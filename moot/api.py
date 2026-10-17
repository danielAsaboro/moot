"""HTTP API and static UI. Every read goes through tools.py; the one write is behind an explicit approve call."""
from __future__ import annotations

from pathlib import Path

from datetime import date

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent, tools
from .graph import DATA, PUBLIC_GRAPH, graph, stats

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

app = FastAPI(title="Moot", version="0.1.0")


def g():
    return graph()


@app.exception_handler(Exception)
async def unhandled(request: Request, ex: Exception):
    """FalkorDB down or a query error: say so plainly instead of a bare 500."""
    msg = str(ex)
    if "Connection" in msg or "refused" in msg.lower() or "timed out" in msg.lower():
        return JSONResponse(503, dict(detail=f"FalkorDB is not reachable: {msg}"))
    return JSONResponse(500, dict(detail=msg))


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
    return dict(audit=a, impact=impact, findings=f, memo=memo, ticket=memo["text"] if memo else agent.draft_ticket(a, impact),
                queries=tools.end_trace())


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
                        status=rec.get("status") or "accepted", verdict=r["verdict"],
                        tools=[dict(id=t, name=checks["tools"][t]["name"], repo=checks["tools"][t]["repo"], unchecked=checks["tools"][t].get("unchecked", []))
                               for t in rec.get("tools", [])],
                        reasons=[dict(id=p["id"], text=p["text"], state=p["state"], evidence=p["evidence"]) for p in a["premises"]]))
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


@app.get("/api/schema")
def schema():
    return tools.schema(g())


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
