"""HTTP API and static UI. Every read goes through tools.py; the one write is behind an explicit approve call."""
from __future__ import annotations

from pathlib import Path

from datetime import date

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent, tools
from .graph import graph, stats

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
    return dict(audit=a, impact=impact, findings=f, ticket=agent.draft_ticket(a, impact), queries=tools.end_trace())


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
