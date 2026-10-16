"""Integration tests against a live FalkorDB (skipped when none is reachable). Uses its own tenant graph."""
import os
import pytest

from moot.graph import connect, seed
from moot import tools, agent
from moot.corpus import spec

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def g():
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    graph = db.select_graph("moot_test")
    seed(graph, fresh=True)
    yield graph
    graph.delete()


def test_seed_is_idempotent(g):
    before = tools.schema(g)
    a = seed(g); b = seed(g)
    assert a == b


def test_ledger_matches_ground_truth(g):
    expected = {d["id"]: d["expected"] for d in spec.DECISIONS}
    got = {r["id"]: r["verdict"] for r in tools.ledger(g, spec.AS_OF, 4)}
    assert got == expected


def test_depth_changes_verdict(g):
    assert tools.audit_decision(g, "D01", spec.AS_OF, 1)["verdict"] == "HOLDS"
    assert tools.audit_decision(g, "D01", spec.AS_OF, 2)["verdict"] == "MOOT"


def test_as_of_time_travel(g):
    assert tools.audit_decision(g, "D07", "2025-06-01", 4)["verdict"] == "HOLDS"
    assert tools.audit_decision(g, "D07", "2026-01-01", 4)["verdict"] == "MOOT"


def test_not_in_graph(g):
    assert tools.audit_decision(g, "D99")["verdict"] == "NOT_IN_GRAPH"
    assert agent.ask(g, "why is the sky blue")["outcome"] == "unknown_entity"


def test_shared_premise_impact(g):
    r = tools.premise_impact(g, "p_gateway_limit")
    assert {d["id"] for d in r["decisions"]} == {"D01", "D02", "D03"}


def test_narration_validator_rejects_foreign_ids():
    ok, bad = agent.validate("MOOT because of [PR-999].", {"D01", "PR-412"})
    assert not ok and bad == ["PR-999"]


def test_finding_memory(g):
    tools.write_finding(g, "D08", "MOOT", spec.AS_OF, 4, ["doc-allhands-2026-04"], "test")
    r = agent.ask(g, "why do we keep the monolith", spec.AS_OF, 4)
    assert r["outcome"] == "answered_from_memory"


def test_time_travel_hides_undecided(g):
    # D01 was decided 2025-02-10: before that it is not in the ledger and audits as NOT_YET
    ids = {r["id"] for r in tools.ledger(g, "2025-01-31", 4)}
    assert "D01" not in ids
    assert tools.audit_decision(g, "D01", "2025-01-31", 4)["verdict"] == "NOT_YET"
    assert tools.audit_decision(g, "D01", "2026-01-31", 4)["verdict"] == "HOLDS"


def test_timeline_is_monotone_until_evidence_lands(g):
    pts = tools.timeline(g, "2025-01-01", spec.AS_OF, 4)
    assert pts[0]["counts"].get("MOOT", 0) == 0
    assert pts[-1]["counts"]["MOOT"] == 12
    assert "D01" in next(p for p in pts if p["as_of"].startswith("2026-03"))["newly_moot"]


def test_trace_records_queries(g):
    tools.start_trace()
    tools.audit_decision(g, "D01", spec.AS_OF, 4)
    q = tools.end_trace()
    assert len(q) >= 2 and all(not x["write"] for x in q) and all(x["ms"] >= 0 for x in q)
    assert tools.end_trace() == []  # closed


def test_api_validation_and_errors(g, monkeypatch):
    from fastapi.testclient import TestClient
    from moot import api
    monkeypatch.setattr(api, "g", lambda: g)
    c = TestClient(api.app)
    assert c.get("/api/ledger?as_of=nope").status_code == 422
    assert c.get("/api/decision/D99").status_code == 404
    assert c.post("/api/ask", json={"question": "   "}).status_code == 422
    assert c.post("/api/findings", json={"decision_id": "D01", "verdict": "MAYBE", "as_of": spec.AS_OF}).status_code == 422
    r = c.get("/api/decision/D01?as_of=2026-10-16").json()
    assert r["audit"]["verdict"] == "MOOT" and r["queries"]
    assert c.get("/api/timeline").json()["points"][-1]["counts"]["MOOT"] >= 1
    unknown = c.post("/api/ask", json={"question": "What is our policy on blockchain?"}).json()
    assert unknown["outcome"] == "unknown_entity"


def test_mcp_server_lists_tools():
    import asyncio
    from moot import mcp_server
    names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert {"find_decision", "audit_decision", "premise_impact", "trace_document", "ledger", "ask", "record_finding"} <= names


def test_document_endpoint_serves_source_text(g, monkeypatch):
    from fastapi.testclient import TestClient
    from moot import api
    monkeypatch.setattr(api, "g", lambda: g)
    c = TestClient(api.app)
    d = c.get("/api/document/PR-412").json()
    assert d["kind"] == "pr" and "100 MB" in d["text"]
    assert c.get("/api/document/src:D01").json()["kind"] == "adr"
    assert c.get("/api/document/nope").status_code == 404
