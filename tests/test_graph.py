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
    assert {"find_decision", "audit_decision", "premise_impact", "trace_document", "ledger", "ask", "record_finding",
            "orphaned_decisions", "record_handover", "reopen_memo", "what_if", "riskiest_reasons"} <= names


def test_document_endpoint_serves_source_text(g, monkeypatch):
    from fastapi.testclient import TestClient
    from moot import api
    monkeypatch.setattr(api, "g", lambda: g)
    c = TestClient(api.app)
    d = c.get("/api/document/PR-412").json()
    assert d["kind"] == "pr" and "100 MB" in d["text"]
    assert c.get("/api/document/src:D01").json()["kind"] == "adr"
    assert c.get("/api/document/nope").status_code == 404


def test_orphans_route_up_the_reporting_line(g):
    o = tools.orphans(g, spec.AS_OF, 4)
    groups = {x["person"]["id"]: x for x in o["groups"]}
    assert set(groups) == {"ada", "lena"}
    assert {d["id"] for d in groups["ada"]["decisions"]} == {"D01", "D09"}
    assert {d["id"] for d in groups["lena"]["decisions"]} == {"D04", "D19"}
    # Lena reported to Ada, who had already left, so it goes one level further up
    assert groups["lena"]["successor"]["id"] == "kwame"
    assert [n["id"] for n in groups["lena"]["successor"]["chain"]] == ["lena", "ada", "kwame"]


def test_successor_uses_the_reporting_line_of_the_day(g):
    # Ada reported to Tomi until Kwame joined on 2025-08-01
    assert tools.successor(g, "ada", "2025-07-01", "2025-07-01")["id"] == "tomi"
    assert tools.successor(g, "ada", "2026-05-15", spec.AS_OF)["id"] == "kwame"


def test_reopen_memo(g):
    m = tools.reopen_memo(g, "D01", spec.AS_OF, 4)
    assert [b["premise"]["id"] for b in m["broken"]] == ["p_gateway_limit"]
    assert m["broken"][0]["evidence"]["id"] == "PR-412" and m["cites"] == ["PR-412"]
    assert {x["id"] for x in m["affected"]} == {"D02", "D03"}
    assert m["suggested_owner"]["id"] == "kwame"
    assert "PR-412" in m["text"] and "Kwame" in m["text"]
    d4 = tools.reopen_memo(g, "D04", spec.AS_OF, 4)
    assert d4["broken"][0]["state"] == "disputed" and d4["broken"][0]["reaffirmed_by"]["id"] == "chat-2025-10-02-search"
    assert tools.reopen_memo(g, "D06", spec.AS_OF, 4)["broken"] == []


def test_what_if_and_riskiest(g):
    w = tools.what_if(g, "p_soc2_cert", spec.AS_OF, 4)
    assert {x["id"] for x in w["decisions"] if x["flips"]} == {"D06", "D22", "D27"} and w["would_fall"] == 3
    assert all(x["after"] == "MOOT" for x in w["decisions"])
    # depth matters: the root reason is two hops from each decision
    assert tools.what_if(g, "p_soc2_cert", spec.AS_OF, 1)["decisions"] == []
    b = tools.what_if(g, "p_infra_budget", spec.AS_OF, 4)
    assert {x["id"] for x in b["decisions"]} == {"D10", "D17", "D19", "D26"} and b["already_moot"] == 1
    r = tools.riskiest_reasons(g, spec.AS_OF, 4)["reasons"]
    assert r[0]["id"] == "p_infra_budget" and r[0]["standing"] == 3
    assert r[1]["id"] == "p_soc2_cert"
    assert tools.find_premise(g, "what if we no longer need SOC 2")[0]["id"] == "p_soc2_cert"
    assert tools.find_premise(g, "if churn goes above 5%") == []


def test_handover_and_reopen_api(g, monkeypatch):
    from fastapi.testclient import TestClient
    from moot import api
    monkeypatch.setattr(api, "g", lambda: g)
    c = TestClient(api.app)
    assert c.get("/api/orphans", params={"as_of": spec.AS_OF}).json()["count"] == 4
    r = c.post("/api/handover", json={"decision_id": "D19", "to": "kwame", "as_of": spec.AS_OF}).json()
    assert r["to_name"] == "Kwame Boateng" and r["from_id"] == "lena"
    assert c.get("/api/orphans", params={"as_of": spec.AS_OF}).json()["count"] == 3
    assert tools.decision_owner(g, "D19", spec.AS_OF)["id"] == "kwame"
    assert tools.decision_owner(g, "D19", "2026-09-01")["id"] == "lena"  # time travel still shows the old owner
    assert c.post("/api/handover", json={"decision_id": "D19", "to": "ada", "as_of": spec.AS_OF}).status_code == 422  # Ada has left
    f = c.post("/api/reopen", json={"decision_id": "D01", "as_of": spec.AS_OF}).json()
    assert f["kind"] == "reopen" and f["assignee"] == "kwame" and f["cites"] == ["PR-412"]
    assert tools.findings(g, "D01")[0]["assignee"] == "Kwame Boateng"
    assert c.post("/api/reopen", json={"decision_id": "D06", "as_of": spec.AS_OF}).status_code == 422
    w = c.get("/api/whatif", params={"q": "What if we no longer need SOC 2?", "as_of": spec.AS_OF}).json()
    assert w["premise"]["id"] == "p_soc2_cert" and w["queries"]
    assert c.get("/api/whatif", params={"q": "if churn goes above 5%"}).json()["found"] is False
    assert c.get("/api/risky", params={"as_of": spec.AS_OF}).json()["reasons"][0]["id"] == "p_infra_budget"
