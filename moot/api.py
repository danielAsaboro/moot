"""HTTP API and static UI. Every read goes through tools.py; the one write is behind an explicit approve call."""
from __future__ import annotations

import json
import os
import time
from contextvars import ContextVar
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent, answer, mapdata, people as people_mod, snapshot, tools
from .graph import BACKTEST_GRAPH, DATA, GH_PREFIX, PUBLIC_GRAPH, connect, graph, stats

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"                      # legacy UI, served at /legacy
UI = ROOT / "frontend" / "out"          # Next.js static export (`make ui`), served at /

app = FastAPI(title="Moot", version="0.1.0")
# Only the Next.js dev server (`make ui-dev`) needs cross-origin access; the built UI is same-origin.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001", "http://127.0.0.1:3001"],
                   allow_methods=["GET", "POST"], allow_headers=["content-type"])


if snapshot.enabled():
    _SNAP = snapshot.load()

    @app.middleware("http")
    async def serve_snapshot(request: Request, call_next):
        """Hosts without FalkorDB (Vercel) answer from the recorded snapshot; see moot/snapshot.py."""
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)
        body = None
        if request.method == "POST":
            try:
                body = await request.json()
            except Exception:
                body = None
        hit = _SNAP.get(snapshot.key(request.method, path, request.url.query, body))
        if hit:
            return Response(hit["body"], status_code=hit["status"], media_type=hit["type"])
        if path == "/api/search":
            return JSONResponse([])  # type-ahead hints only; the Ask answer itself says when it is outside the snapshot
        if request.method == "GET" and path.startswith("/api/document/"):
            return await call_next(request)  # read from data/corpus, no graph needed
        return JSONResponse({"detail": snapshot.READ_ONLY}, status_code=503)


# Every route reads the graph named by `?graph=` (the tenant by default): the demo company, the real public ADRs, the
# backtest, or any repository brought in with `moot ingest-github`. A name outside that list is refused.
_selected: ContextVar[str | None] = ContextVar("moot_graph", default=None)
_known: dict = dict(at=0.0, names=set())


def known_graphs() -> set[str]:
    if time.time() - _known["at"] > 30:
        try:
            names = set(connect().list_graphs())
        except Exception:
            names = set()
        _known.update(at=time.time(), names={n for n in names if n.startswith(GH_PREFIX)} | {graph().name, PUBLIC_GRAPH, BACKTEST_GRAPH})
    return _known["names"]


@app.middleware("http")
async def select_graph(request: Request, call_next):
    name = request.query_params.get("graph")
    if name and name != graph().name and name not in known_graphs():
        return JSONResponse({"detail": f"no graph named {name}; GET /api/graphs lists them"}, status_code=422)
    token = _selected.set(name or None)
    try:
        return await call_next(request)
    finally:
        _selected.reset(token)


def g():
    return graph(_selected.get())


@app.exception_handler(Exception)
async def unhandled(request: Request, ex: Exception):
    """FalkorDB down or a query error: say so plainly instead of a bare 500."""
    msg = str(ex)
    if "Connection" in msg or "refused" in msg.lower() or "timed out" in msg.lower():
        return JSONResponse(status_code=503, content=dict(detail=f"FalkorDB is not reachable: {msg}"))
    return JSONResponse(status_code=500, content=dict(detail=msg))


def as_of_param(as_of: str | None) -> str | None:
    if not as_of:
        return None
    try:
        return date.fromisoformat(as_of).isoformat()
    except ValueError:
        raise HTTPException(422, "as_of must be an ISO date like 2026-03-01")


@app.get("/api/health")
def health():
    try:
        return dict(ok=True, tenant=g().name, stats=stats(g()), model=agent.has_model())
    except Exception as ex:  # FalkorDB down
        raise HTTPException(503, f"FalkorDB unreachable: {ex}")


@app.get("/api/ledger")
def ledger(as_of: str | None = None, depth: int = Query(4, ge=1, le=6)):
    as_of = as_of_param(as_of)
    return dict(as_of=as_of or tools.today(), depth=depth, decisions=tools.ledger(g(), as_of, depth))


@app.get("/api/timeline")
def timeline(start: str = "2025-01-01", end: str | None = None, depth: int = Query(4, ge=1, le=6)):
    """The ledger re-run at every month end: how many decisions had quietly gone MOOT by then."""
    return dict(depth=depth, points=tools.timeline(g(), as_of_param(start) or "2025-01-01", as_of_param(end), depth))


@app.get("/api/map")
def network_map(as_of: str | None = None, depth: int = Query(4, ge=1, le=6)):
    """The whole network for the map view, with every verdict and reason state at each month end. Read-only."""
    return mapdata.export(g(), as_of_param(as_of), depth)


@app.get("/api/decision/{decision_id}")
def decision(decision_id: str, as_of: str | None = None, depth: int = Query(4, ge=1, le=6)):
    as_of = as_of_param(as_of)
    tools.start_trace()
    a = tools.audit_decision(g(), decision_id, as_of, depth)
    if not a["found"]:
        tools.end_trace()
        raise HTTPException(404, f"{decision_id} is not in the graph")
    impact = [tools.premise_impact(g(), p["id"]) for p in a["premises"] if p["state"] in ("expired", "disputed")]
    f = tools.findings(g(), decision_id)
    memo = tools.reopen_memo(g(), decision_id, as_of, depth) if a["verdict"] in ("MOOT", "DISPUTED") else None
    gate = tools.check_action(g(), decision_id, as_of)
    hist = tools.verdict_history(g(), decision_id, as_of, depth)
    know = people_mod.knowers(g(), decision_id, as_of)
    return dict(audit=a, impact=impact, findings=f, memo=memo, gate=gate, history=hist, knowers=know, ticket=memo["text"] if memo else agent.draft_ticket(a, impact),
                queries=tools.end_trace())


@app.get("/api/history/{decision_id}")
def history(decision_id: str, as_of: str | None = None, depth: int = Query(4, ge=1, le=6)):
    """Since when? Every verdict the decision has had, re-audited on each date something in its subgraph happened."""
    r = tools.verdict_history(g(), decision_id, as_of_param(as_of), depth)
    if not r["found"]:
        raise HTTPException(404, f"{decision_id} is not in the graph")
    return r


@app.get("/api/people")
def people(as_of: str | None = None):
    """Everyone still here: what they own, what only they know (bus factor 1), and betweenness on the knowledge projection."""
    tools.start_trace()
    r = people_mod.people(g(), as_of_param(as_of))
    r["queries"] = tools.end_trace()
    return r


@app.get("/api/people/{person_id}/departure")
def departure(person_id: str, as_of: str | None = None):
    """What leaves with a person: computed on a GRAPH.COPY with them removed (algo.WCC). The company graph is not written."""
    tools.start_trace()
    r = people_mod.departure(g(), person_id, as_of_param(as_of))
    if not r["found"]:
        tools.end_trace()
        raise HTTPException(404, f"{person_id} is not in the graph")
    r["queries"] = tools.end_trace()
    return r


@app.get("/api/knowers/{decision_id}")
def knowers(decision_id: str, as_of: str | None = None):
    """Who knows why a decision was made: its owner, who wrote its record, who wrote evidence on its reasons."""
    r = people_mod.knowers(g(), decision_id, as_of_param(as_of))
    if not r["found"]:
        raise HTTPException(404, f"{decision_id} is not in the graph")
    return r


@app.get("/api/spof")
def spof(as_of: str | None = None, limit: int = Query(10, ge=1, le=50)):
    """Reasons two or more live decisions rest on that only one document, or one person still here, vouches for."""
    return people_mod.premise_spof(g(), as_of_param(as_of), limit)


@app.get("/api/gate/{decision_id}")
def gate(decision_id: str, as_of: str | None = None, graph_name: str | None = Query(None, alias="graph")):
    """The validity gate, for agents: may I act on (enforce, rely on, renew) this decision? ALLOW | DENY | REVALIDATE with the path.
    Read-only. `graph` picks the tenant (default) or the public-ADR graph."""
    gr = _graph_for(graph_name)
    tools.start_trace()
    r = tools.check_action(gr, decision_id, as_of_param(as_of))
    r["queries"] = tools.end_trace()
    return r


def _graph_for(graph_name: str | None):
    return graph(graph_name) if graph_name else g()  # the middleware has already refused unknown names


@app.get("/api/packet/{decision_id}")
def packet(decision_id: str, as_of: str | None = None, format: str = Query("json", pattern="^(json|md)$"),
           graph_name: str | None = Query(None, alias="graph")):
    """The evidence packet behind one verdict: gate, reasons, every receipt with its quote and dates, owner rulings, the
    re-open memo, caveats, a synthetic-data flag and the snapshot digests. `format=md` downloads it as Markdown."""
    pk = tools.evidence_packet(_graph_for(graph_name), decision_id, as_of_param(as_of))
    if not pk["found"]:
        raise HTTPException(404, f"{decision_id} is not in the graph")
    if format == "md":
        return PlainTextResponse(tools.packet_markdown(pk), media_type="text/markdown",
                                 headers={"Content-Disposition": f'attachment; filename="moot-{decision_id}-{pk["as_of"]}.md"'})
    return pk


class Ruling(BaseModel):
    decision_id: str
    premise_id: str
    holds: bool
    as_of: str
    by: str | None = None
    note: str = ""


@app.post("/api/ruling")
def ruling(body: Ruling):
    """Approval gate for an owner's ruling on a reason the gate could not vouch for (disputed, unchecked, unevidenced).
    Writes a dated SUPPORTS or CONTRADICTS edge from a Finding; the next audit cites it until newer evidence lands."""
    r = tools.write_ruling(g(), body.decision_id, body.premise_id, body.holds, as_of_param(body.as_of), body.by, body.note.strip()[:500])
    if r.get("error"):
        raise HTTPException(422, r["error"])
    return r


@app.get("/api/search")
def search(q: str):
    return tools.find_decision(g(), q)


@app.get("/api/premise/{premise_id}")
def premise(premise_id: str):
    r = tools.premise_impact(g(), premise_id)
    if not r["found"]:
        raise HTTPException(404, "not in the graph")
    return r


@app.get("/api/trace/{evidence_id}")
def trace(evidence_id: str):
    tools.start_trace()
    r = tools.trace_document(g(), evidence_id)
    if not r["found"]:
        tools.end_trace()
        raise HTTPException(404, f"{evidence_id} is not in the graph")
    r["queries"] = tools.end_trace()
    return r


class Ask(BaseModel):
    question: str
    as_of: str | None = None
    depth: int = 4


@app.post("/api/ask")
def ask(body: Ask):
    if not body.question.strip():
        raise HTTPException(422, "ask a question")
    tools.start_trace()
    r = agent.ask(g(), body.question.strip()[:500], as_of_param(body.as_of), max(1, min(body.depth, 6)))
    r["queries"] = tools.end_trace()
    return r


class AnswerBody(BaseModel):
    question: str = ""
    as_of: str | None = None
    depth: int = 4
    tool: str | None = None
    input: dict[str, str] | None = None


@app.post("/api/answer")
def answer_route(body: AnswerBody):
    """Search-first answers: the question picks one read-only tool (rules, or a model from the same list) and its rows come
    back with every query it ran. A follow-up can name the tool and input directly."""
    if not body.question.strip() and not body.tool:
        raise HTTPException(422, "ask a question")
    tools.start_trace()
    try:
        r = answer.answer(g(), body.question.strip()[:500], as_of_param(body.as_of), max(1, min(body.depth, 6)), body.tool, body.input)
    except KeyError as ex:
        tools.end_trace()
        raise HTTPException(422, f"not a read-only answer tool: {ex}")
    r["queries"] = tools.end_trace()
    return r


class Approve(BaseModel):
    decision_id: str
    verdict: str
    as_of: str
    depth: int = 4
    cites: list[str] = []
    note: str = ""


@app.post("/api/findings")
def approve(body: Approve):
    """The approval gate. The UI shows the draft first; this call records it as a Finding node."""
    if body.verdict not in ("MOOT", "DISPUTED", "HOLDS", "UNDOCUMENTED", "RETIRED"):
        raise HTTPException(422, "unknown verdict")
    as_of_param(body.as_of)
    return tools.write_finding(g(), body.decision_id, body.verdict, body.as_of, body.depth, body.cites, body.note)


@app.get("/api/orphans")
def orphans(as_of: str | None = None, depth: int = Query(4, ge=1, le=6)):
    """Live decisions whose owner has left, grouped by who left, each routed up the reporting line to someone still here."""
    tools.start_trace()
    r = tools.orphans(g(), as_of_param(as_of), depth)
    r["queries"] = tools.end_trace()
    return r


class Handover(BaseModel):
    decision_id: str
    to: str
    as_of: str


@app.post("/api/handover")
def handover(body: Handover):
    """Approval gate for a handover: writes a new dated OWNS edge. Nothing changes until this is called."""
    r = tools.handover(g(), body.decision_id, body.to, as_of_param(body.as_of))
    if r.get("error"):
        raise HTTPException(422, r["error"])
    return r


@app.get("/api/reopen/{decision_id}")
def reopen_draft(decision_id: str, as_of: str | None = None, depth: int = Query(4, ge=1, le=6)):
    m = tools.reopen_memo(g(), decision_id, as_of_param(as_of), depth)
    if not m["found"]:
        raise HTTPException(404, f"{decision_id} is not in the graph")
    return m


class Reopen(BaseModel):
    decision_id: str
    as_of: str
    depth: int = 4
    owner_id: str | None = None


@app.post("/api/reopen")
def reopen(body: Reopen):
    """Approve the re-open memo. The memo is rebuilt from the graph here, so the client cannot write text the rows do not support."""
    as_of = as_of_param(body.as_of)
    m = tools.reopen_memo(g(), body.decision_id, as_of, max(1, min(body.depth, 6)))
    if not m["found"]:
        raise HTTPException(404, f"{body.decision_id} is not in the graph")
    if not m["broken"]:
        raise HTTPException(422, "no reason has broken, so there is nothing to re-open")
    owner = body.owner_id or m["suggested_owner"]["id"]
    f = tools.write_finding(g(), body.decision_id, m["verdict"], as_of, m["depth"], m["cites"], m["text"], kind="reopen", assignee=owner)
    return dict(f, memo=m)


@app.get("/api/whatif")
def whatif(premise: str | None = None, q: str | None = None, as_of: str | None = None, depth: int = Query(4, ge=1, le=6)):
    """Pretend a reason broke today: which decisions rest on it, through which chain, and what they would flip to."""
    tools.start_trace()
    cands = []
    if not premise:
        cands = tools.find_premise(g(), q or "")
        if not cands:
            tools.end_trace()
            return dict(found=False, question=q, candidates=[], answer="No reason in the graph matches that. Moot only tests reasons someone wrote down.")
        premise = cands[0]["id"]
    r = tools.what_if(g(), premise, as_of_param(as_of), depth)
    if not r["found"]:
        tools.end_trace()
        raise HTTPException(404, f"{premise} is not in the graph")
    r["candidates"] = cands
    r["question"] = q
    r["queries"] = tools.end_trace()
    return r


@app.get("/api/risky")
def risky(as_of: str | None = None, depth: int = Query(4, ge=1, le=6), limit: int = Query(10, ge=1, le=50)):
    """Reasons ranked by how many standing decisions sit below them."""
    return tools.riskiest_reasons(g(), as_of_param(as_of), depth, limit)


@app.get("/api/realworld")
def realworld():
    """Real public ADRs from five GitHub repositories, audited by the same path queries against dated GitHub and OSV checks."""
    import json
    snap = DATA / "realworld" / "checks.json"
    if not snap.exists():
        raise HTTPException(404, "no real-world snapshot; run `moot realworld`")
    checks = json.loads(snap.read_text())
    pg = graph(PUBLIC_GRAPH)
    as_of = checks["summary"]["checked_on"]
    tools.start_trace()
    rows = tools.ledger(pg, as_of, 2)
    if not rows:
        tools.end_trace()
        raise HTTPException(503, f"the {PUBLIC_GRAPH} graph is empty; run `moot seed`")
    recs = {r["id"]: r for r in checks["records"]}
    out = []
    for r in rows:
        a = tools.audit_decision(pg, r["id"], as_of, 2)
        rec = recs.get(r["id"], {})
        out.append(dict(id=r["id"], title=r["title"], repo=rec.get("repo"), url=rec.get("url"), date=r["decided_on"], quote=rec.get("quote"),
                        status=rec.get("status") or "accepted", verdict=r["verdict"], retired=rec.get("retired"),
                        gate=tools.check_action(pg, r["id"], as_of)["gate"],
                        tools=[dict(id=t, name=checks["tools"][t]["name"], repo=checks["tools"][t]["repo"], unchecked=checks["tools"][t].get("unchecked", []))
                               for t in rec.get("tools", [])],
                        reasons=[dict(id=p["id"], text=p["text"], state=p["state"], unchecked=p.get("unchecked"), evidence=p["evidence"])
                                 for p in a["premises"]]))
    shared = [dict(tool=t["name"], records=[r["id"] for r in checks["records"] if tid in r["tools"]])
              for tid, t in checks["tools"].items() if sum(tid in r["tools"] for r in checks["records"]) > 1]
    return dict(summary=checks["summary"], decisions=out, shared=shared, queries=tools.end_trace())


_DOCS: dict[str, dict] | None = None


@app.get("/api/document/{doc_id}")
def document(doc_id: str):
    """The source text behind an evidence id (ADR, PR, ticket, chat message or doc), read from data/corpus."""
    global _DOCS
    if _DOCS is None:
        from .ingest.extract import load_documents
        _DOCS = {d["id"]: d for d in load_documents()}
        for k in list(_DOCS):
            _DOCS[f"src:{k}"] = _DOCS[k]
    d = _DOCS.get(doc_id)
    if not d:
        raise HTTPException(404, f"no source text for {doc_id}")
    return dict(id=doc_id, kind=d["kind"], title=d["title"], date=d["date"], author=d["author"], path=d["path"], text=d["text"])


@app.get("/api/evals")
def evals():
    """The committed eval results (eval/results*.json), so the landing page quotes the same numbers `moot verify` checks."""
    import json
    out = {}
    for f in sorted((ROOT / "eval").glob("results*.json")):
        out[f.stem.removeprefix("results").lstrip("_") or "retrieval"] = json.loads(f.read_text())
    return out


GRAPH_INFO = {
    "larkspur": dict(title="Larkspur (demo company)", kind="demo", source="data/corpus: a synthetic 30-person company"),
    PUBLIC_GRAPH: dict(title="25 real public ADRs", kind="real", source="5 GitHub repositories, checked against GitHub and OSV"),
    BACKTEST_GRAPH: dict(title="Backtest: 97 tool decisions from 30 repos", kind="backtest", source="ADR git history, replayed monthly", as_of="2026-10-17"),
}


_graphs_cache: dict = dict(at=0.0, body=None)
GRAPHS_TTL = 60  # seconds; the list only changes on a seed or an ingest, and an ingest clears it


@app.get("/api/graphs")
def graphs():
    """Every graph the UI and API can read: the demo company, the real ADRs, the backtest and each ingested repository."""
    if _graphs_cache["body"] is not None and time.time() - _graphs_cache["at"] < GRAPHS_TTL:
        return _graphs_cache["body"]
    body = _list_graphs()
    _graphs_cache.update(at=time.time(), body=body)
    return body


def _list_graphs() -> dict:
    from .connectors import github as gh
    out = []
    for name in sorted(known_graphs(), key=lambda n: (n != graph().name, n != PUBLIC_GRAPH, n != BACKTEST_GRAPH, n)):
        info = dict(GRAPH_INFO.get(name) or dict(title=name, kind="github", source=""))
        summ = gh.summary_for_graph(name)
        if summ:
            info.update(title=summ["repo"], source=f"{summ['folder']} in github.com/{summ['repo']}, read {summ['read_on']}", as_of=summ["read_on"],
                        url=f"https://github.com/{summ['repo']}")
        if name == PUBLIC_GRAPH and (DATA / "realworld" / "checks.json").exists():
            info["as_of"] = json.loads((DATA / "realworld" / "checks.json").read_text())["summary"]["checked_on"]
        try:
            n = graph(name).ro_query("MATCH (d:Decision) RETURN count(d)").result_set[0][0]
        except Exception:
            n = 0
        if n:
            out.append(dict(name=name, decisions=n, default=name == graph().name, **info))
    return dict(graphs=out, ingest=ingest_allowed())


def ingest_allowed() -> bool:
    """Ingest writes a new graph and calls GitHub; on by default locally, off on a hosted deployment unless MOOT_ALLOW_INGEST=1."""
    return os.getenv("MOOT_ALLOW_INGEST", "0" if os.getenv("VERCEL") else "1") == "1" and not snapshot.enabled()


class Ingest(BaseModel):
    repo: str
    path: str | None = None


@app.post("/api/ingest/github")
def ingest_github(body: Ingest):
    """Bring a public GitHub repository's ADR folder and its pull requests into a new named graph, then audit it."""
    import re as _re
    from .connectors import github as gh
    if not ingest_allowed():
        raise HTTPException(403, "Ingest is off on this deployment. Run it locally: moot ingest-github owner/repo")
    repo = body.repo.strip().removeprefix("https://github.com/").strip("/")
    if not _re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise HTTPException(422, "repo must look like owner/name")
    try:
        gh.ingest(repo, body.path)
    except SystemExit as ex:
        raise HTTPException(422, str(ex))
    _known["at"] = 0
    _graphs_cache["body"] = None
    return gh.audit(repo)


@app.get("/api/schema")
def schema():
    return tools.schema(g())


@app.get("/legacy")
def legacy():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")

# The Next.js export owns every other path: / is the landing page, /app/ Ask, /app/ledger/ the ledger. Mounted last, so /api/* wins.
# Without a build (`make ui`), / falls back to the legacy UI.
if (UI / "index.html").exists():
    app.mount("/", StaticFiles(directory=UI, html=True), name="ui")
else:
    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")
