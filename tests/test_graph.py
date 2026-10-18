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


def test_supersession_is_dated(g):
    # D09 superseded D28 on 2025-07-01; before that D28 was in force (and states no premise)
    assert tools.audit_decision(g, "D28", "2024-12-31", 4)["verdict"] == "UNDOCUMENTED"
    assert tools.audit_decision(g, "D28", "2025-07-31", 4)["superseded_by"] == dict(id="D09", title="Serve EU customers from Frankfurt only",
                                                                                   at="2025-07-01", kind="decision")
    assert {r["id"]: r["verdict"] for r in tools.ledger(g, "2025-06-30", 4)}["D28"] == "UNDOCUMENTED"
    assert {r["id"]: r["verdict"] for r in tools.ledger(g, "2025-07-31", 4)}["D28"] == "RETIRED"


def test_gate(g):
    # the gate audits at full depth: D01 is HOLDS at depth 1, but the gate still denies it on PR-412
    d01 = tools.check_action(g, "D01", spec.AS_OF)
    assert d01["gate"] == "DENY" and d01["depth"] == 6
    assert next(r for r in d01["reasons"] if r["code"] == "premise_expired")["evidence"] == "PR-412"
    assert [n["id"] for n in d01["reasons"][0]["path"]] == ["D01", "p_gateway_path", "p_gateway_limit"]
    d12 = tools.check_action(g, "D12", spec.AS_OF)
    assert d12["gate"] == "ALLOW" and all(b["evidence"] for b in d12["basis"])
    # D06 holds, but one premise below it (p_soc2_cert) has no dated evidence either way: no evidence is not "holds"
    d06 = tools.check_action(g, "D06", spec.AS_OF)
    assert d06["verdict"] == "HOLDS" and d06["gate"] == "REVALIDATE"
    assert [(r["code"], r["premise"]) for r in d06["reasons"]] == [("premise_unevidenced", "p_soc2_cert")]
    assert tools.check_action(g, "D17", spec.AS_OF)["gate"] == "REVALIDATE"   # disputed: the owner has to rule
    assert tools.check_action(g, "D05", spec.AS_OF)["gate"] == "REVALIDATE"   # undocumented
    assert tools.check_action(g, "D28", spec.AS_OF)["gate"] == "DENY"         # retired
    assert tools.check_action(g, "D99", spec.AS_OF)["gate"] == "DENY"         # not in the graph
    assert tools.check_action(g, "D07", "2025-06-01")["gate"] == "REVALIDATE"  # time travel: before PR-350, nothing checked it yet
    assert tools.check_action(g, "D07", spec.AS_OF)["gate"] == "DENY"


def test_structural_answers_skip_the_model(g, monkeypatch):
    monkeypatch.setattr(agent, "_client", lambda: (_ for _ in ()).throw(AssertionError("model called")))
    r = agent.ask(g, "why do we use Postgres for every storage need", spec.AS_OF, 4)
    assert r["audit"]["verdict"] == "UNDOCUMENTED" and r["narration"] == "structural"


def test_evidence_carries_its_author(g):
    a = tools.audit_decision(g, "D01", spec.AS_OF, 4)
    assert [(e["id"], e["author"]) for p in a["premises"] for e in p["evidence"]] == [("PR-412", "Marcus Chen")]


def test_timeline_is_monotone_until_evidence_lands(g):
    pts = tools.timeline(g, "2025-01-01", spec.AS_OF, 4)
    assert pts[0]["counts"].get("MOOT", 0) == 0
    assert pts[-1]["counts"]["MOOT"] == 12
    assert "D01" in next(p for p in pts if p["as_of"].startswith("2026-03"))["newly_moot"]


def test_timeline_agrees_with_the_ledger_at_every_month_end(g):
    """The timeline reads every event in one query and applies the ledger's rules in Python; it must never disagree."""
    for depth in (1, 4):
        for p in tools.timeline(g, "2024-06-01", spec.AS_OF, depth):
            rows = tools.ledger(g, p["as_of"], depth)
            counts: dict = {}
            for r in rows:
                counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
            assert p["counts"] == counts, p["as_of"]
            assert p["moot"] == sorted(r["id"] for r in rows if r["verdict"] == "MOOT")


def test_one_client_per_server():
    assert connect() is connect()


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
            "orphaned_decisions", "record_handover", "reopen_memo", "what_if", "riskiest_reasons", "check_action",
            "record_ruling", "evidence_packet"} <= names


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
    gt = c.get("/api/gate/D01", params={"as_of": spec.AS_OF}).json()
    assert gt["gate"] == "DENY" and gt["queries"] and all(not q["write"] for q in gt["queries"])
    assert c.get("/api/gate/D01", params={"graph": "nope"}).status_code == 422
    assert c.get("/api/decision/D12", params={"as_of": spec.AS_OF}).json()["gate"]["gate"] == "ALLOW"
    assert c.get("/api/decision/D06", params={"as_of": spec.AS_OF}).json()["gate"]["gate"] == "REVALIDATE"


# The surfaces must give the same answer, compared at the instants where the answer changes. Two surfaces compared on a
# quiet date would agree even if one read the as-of cutoff wrong. PR-412 contradicts D01's gateway limit on 2026-03-02.
BOUNDARY = [("2026-03-01", "REVALIDATE"), ("2026-03-02", "DENY"), ("2026-03-03", "DENY")]


def test_api_mcp_and_tools_agree_at_the_boundary(g, monkeypatch):
    import asyncio
    import json
    from fastapi.testclient import TestClient
    from moot import api, mcp_server
    monkeypatch.setattr(api, "g", lambda: g)
    monkeypatch.setattr(mcp_server, "graph", lambda name=None: g)
    c = TestClient(api.app)
    for as_of, expected in BOUNDARY:
        http = c.get("/api/gate/D01", params={"as_of": as_of}).json()
        http.pop("queries")
        res = asyncio.run(mcp_server.mcp.call_tool("check_action", {"decision_id": "D01", "as_of": as_of}))
        via_mcp = json.loads(res.content[0].text)
        direct = json.loads(json.dumps(tools.check_action(g, "D01", as_of), default=str))
        assert http == via_mcp == direct, as_of
        assert http["gate"] == expected, as_of   # the cutoff is inclusive: evidence dated as_of counts on as_of
        assert http["snapshot"] == dict(graph=g.name, as_of=as_of, digest=tools.decision_digest(g, "D01"))
    # and the packet carries the same gate and reasons as both surfaces
    for as_of, expected in BOUNDARY:
        pk = c.get("/api/packet/D01", params={"as_of": as_of}).json()
        assert pk["gate"] == expected and pk["reasons"] == c.get("/api/gate/D01", params={"as_of": as_of}).json()["reasons"]


def test_snapshot_digest_is_stable_and_moves_with_the_subgraph(g):
    a = tools.check_action(g, "D12", spec.AS_OF)["snapshot"]["digest"]
    assert tools.check_action(g, "D12", spec.AS_OF)["snapshot"]["digest"] == a
    assert tools.check_action(g, "D12", "2025-06-01")["snapshot"]["digest"] == a   # the digest covers all dates; as_of is separate
    # a write elsewhere in the graph leaves D12's digest alone, but moves the whole-graph digest
    before = tools.graph_digest(g)
    g.query("CREATE (:Evidence {id: 'tmp-unrelated', title: 'x', date: '2026-01-01'})")
    try:
        assert tools.decision_digest(g, "D12") == a and tools.graph_digest(g) != before
    finally:
        g.query("MATCH (e:Evidence {id: 'tmp-unrelated'}) DELETE e")


def test_coverage_refuses_an_empty_or_unevidenced_graph():
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    e = db.select_graph("moot_test_empty")
    e.query("CREATE (:Decision {id: 'X1', title: 'x', decided_on: '2025-01-01'})-[:BECAUSE_OF]->(:Premise {id: 'px', text: 'y'})")
    try:
        r = tools.check_action(e, "X1", "2026-01-01")
        assert r["gate"] == "REVALIDATE" and r["reasons"][0]["code"] == "graph_has_no_evidence"
        e.query("MATCH (n) DETACH DELETE n")
        assert tools.check_action(e, "X1", "2026-01-01")["reasons"][0]["code"] == "graph_empty"
    finally:
        e.delete()


def test_owner_ruling_is_a_dated_edge_the_next_audit_reads(g, monkeypatch):
    from fastapi.testclient import TestClient
    from moot import api
    monkeypatch.setattr(api, "g", lambda: g)
    c = TestClient(api.app)
    assert tools.check_action(g, "D16", spec.AS_OF)["gate"] == "REVALIDATE"
    # a reason that already has evidence takes no ruling, and neither does a premise outside the decision
    assert c.post("/api/ruling", json={"decision_id": "D07", "premise_id": "p_no_rollback", "holds": True, "as_of": spec.AS_OF}).json()["detail"].endswith("takes a ruling")
    assert c.post("/api/ruling", json={"decision_id": "D16", "premise_id": "p_soc2_cert", "holds": True, "as_of": spec.AS_OF}).status_code == 422
    before = tools.decision_digest(g, "D16")
    r = c.post("/api/ruling", json={"decision_id": "D16", "premise_id": "p_eu_market", "holds": True, "as_of": "2026-10-01",
                                    "by": "kwame", "note": "EU is still a target market for 2027."}).json()
    assert r["gate"] == "ALLOW" and r["was"] == "unevidenced"
    after = tools.check_action(g, "D16", spec.AS_OF)
    assert after["gate"] == "ALLOW" and any(b["ruling"] and b["evidence"] == r["id"] for b in after["basis"])
    assert after["snapshot"]["digest"] != before
    # time travel: before the ruling, nothing had checked the premise
    assert tools.check_action(g, "D16", "2026-09-30")["gate"] == "REVALIDATE"
    # newer evidence after the ruling reopens it by the ordinary rules
    g.query("CREATE (e:Evidence {id: 'tmp-eu-exit', title: 'Exit the EU market', kind: 'doc', date: '2026-10-10'}) "
            "WITH e MATCH (p:Premise {id: 'p_eu_market'}) CREATE (e)-[:CONTRADICTS {at: '2026-10-10', quote: 'we leave the EU'}]->(p)")
    try:
        assert tools.check_action(g, "D16", spec.AS_OF)["gate"] == "DENY"
        assert tools.rulings(g, "D16")[0]["by"] == "Kwame Boateng"
    finally:
        g.query("MATCH (e:Evidence {id: 'tmp-eu-exit'}) DETACH DELETE e")


def test_evidence_that_is_stated_later_does_not_count_before_it_is_known(g):
    # a document written on 2026-07-01 says the gateway limit changed back on 2026-06-01; on 2026-06-15 nobody knew yet
    g.query("CREATE (e:Evidence {id: 'tmp-late', title: 'Limit back to 10 MB', kind: 'doc', date: '2026-07-01'}) WITH e "
            "MATCH (p:Premise {id: 'p_gateway_limit'}) CREATE (e)-[:SUPPORTS {at: '2026-06-01', stated: '2026-07-01', quote: 'reverted'}]->(p)")
    try:
        lim = lambda a: next(p for p in tools.audit_decision(g, "D02", a, 4)["premises"] if p["id"] == "p_gateway_limit")
        assert lim("2026-06-15")["state"] == "expired" and [e["id"] for e in lim("2026-06-15")["evidence"]] == ["PR-412"]
        assert lim("2026-07-01")["state"] == "disputed"
        assert next(e for e in lim("2026-07-01")["evidence"] if e["id"] == "tmp-late")["stated"] == "2026-07-01"
        assert {r["id"]: r["verdict"] for r in tools.ledger(g, "2026-06-15", 4)}["D02"] == "MOOT"
        assert {r["id"]: r["verdict"] for r in tools.ledger(g, "2026-07-01", 4)}["D02"] == "DISPUTED"
    finally:
        g.query("MATCH (e:Evidence {id: 'tmp-late'}) DETACH DELETE e")


def test_memory_expires_when_anything_below_changes(g):
    tools.write_finding(g, "D14", "HOLDS", spec.AS_OF, 6, [], "test")
    q = next(d["title"] for d in spec.DECISIONS if d["id"] == "D14")
    assert agent.ask(g, q, spec.AS_OF, 4)["outcome"] == "answered_from_memory"
    deep = tools.audit_decision(g, "D14", spec.AS_OF, 6)["premises"][-1]["id"]
    g.query("CREATE (e:Evidence {id: 'tmp-deep', title: 'x', kind: 'doc', date: '2026-01-01'}) WITH e "
            "MATCH (p:Premise {id: $p}) CREATE (e)-[:SUPPORTS {at: '2026-01-01'}]->(p)", {"p": deep})
    try:
        assert agent.ask(g, q, spec.AS_OF, 4)["outcome"] == "answered_with_path"
    finally:
        g.query("MATCH (e:Evidence {id: 'tmp-deep'}) DETACH DELETE e")


def test_packet_markdown_and_cli(g, monkeypatch):
    from fastapi.testclient import TestClient
    from moot import api
    monkeypatch.setattr(api, "g", lambda: g)
    c = TestClient(api.app)
    r = c.get("/api/packet/D01", params={"as_of": spec.AS_OF, "format": "md"})
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert "PR-412" in r.text and "Synthetic data" in r.text and "decision digest" in r.text
    assert c.get("/api/packet/D99").status_code == 404
    pk = c.get("/api/packet/D01", params={"as_of": spec.AS_OF}).json()
    assert pk["synthetic"] and pk["snapshot"]["graph_digest"].startswith("sha256:") and pk["memo"]
