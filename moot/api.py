"""HTTP API and static UI. Every read goes through tools.py; the one write is behind an explicit approve call."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent, tools
from .graph import graph, stats

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

app = FastAPI(title="Moot", version="0.1.0")


def g():
    return graph()


@app.get("/api/health")
def health():
    try:
        return dict(ok=True, tenant=g().name, stats=stats(g()), model=agent.has_model())
    except Exception as ex:  # FalkorDB down
        raise HTTPException(503, f"FalkorDB unreachable: {ex}")


@app.get("/api/ledger")
def ledger(as_of: str | None = None, depth: int = Query(4, ge=1, le=6)):
    return dict(as_of=as_of or tools.today(), depth=depth, decisions=tools.ledger(g(), as_of, depth))


@app.get("/api/decision/{decision_id}")
def decision(decision_id: str, as_of: str | None = None, depth: int = Query(4, ge=1, le=6)):
    a = tools.audit_decision(g(), decision_id, as_of, depth)
    if not a["found"]:
        raise HTTPException(404, "not in the graph")
    impact = [tools.premise_impact(g(), p["id"]) for p in a["premises"] if p["state"] in ("expired", "disputed")]
    return dict(audit=a, impact=impact, findings=tools.findings(g(), decision_id), ticket=agent.draft_ticket(a, impact))


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
    r = tools.trace_document(g(), evidence_id)
    if not r["found"]:
        raise HTTPException(404, "not in the graph")
    return r


class Ask(BaseModel):
    question: str
    as_of: str | None = None
    depth: int = 4


@app.post("/api/ask")
def ask(body: Ask):
    return agent.ask(g(), body.question, body.as_of, max(1, min(body.depth, 6)))


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
    return tools.write_finding(g(), body.decision_id, body.verdict, body.as_of, body.depth, body.cites, body.note)


@app.get("/api/schema")
def schema():
    return tools.schema(g())


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
