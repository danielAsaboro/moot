"""Search-first answers: a question picks one read-only tool. Integration tests against a live FalkorDB (skipped when
none is reachable), on their own tenant graph."""
from types import SimpleNamespace

import pytest

from moot import agent, answer, tools
from moot.corpus import spec
from moot.graph import connect, seed

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def g():
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    graph = db.select_graph("moot_test_answer")
    seed(graph, fresh=True)
    yield graph
    graph.delete()


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    monkeypatch.setattr(agent, "_client", lambda: None)


ROUTES = [
    ("Why do we cap uploads at 10 MB?", "audit_decision", {"decision_id": "D01"}),
    ("Can an agent change the Friday deploy freeze?", "check_action", {"decision_id": "D07"}),
    ("is it safe for a bot to rotate the api keys?", "check_action", {"decision_id": "D06"}),
    ("What if we no longer need SOC 2?", "what_if", {"reason": "p_soc2_cert"}),
    ("what if the gateway limit changed", "what_if", {"reason": "p_gateway_limit"}),
    ("What did Ada own?", "orphaned_decisions", {"person": "ada"}),
    ("what does Kwame own", "ledger", {"owner": "kwame"}),
    ("who left?", "orphaned_decisions", {}),
    ("Show the evidence for D17", "evidence_packet", {"decision_id": "D17"}),
    ("proof behind keeping the monolith", "evidence_packet", {"decision_id": "D08"}),
    ("Which decisions are moot?", "ledger", {"verdict": "MOOT"}),
    ("which rules are disputed", "ledger", {"verdict": "DISPUTED"}),
    ("re-open the upload limit decision", "reopen_memo", {"decision_id": "D01"}),
    ("who owns the search index rebuild", "decision_owner", {"decision_id": "D04"}),
    ("why do we deploy to a single region in virginia", "audit_decision", {"decision_id": "D28"}),
    ("D12", "audit_decision", {"decision_id": "D12"}),
]


@pytest.mark.parametrize("question,tool,inp", ROUTES)
def test_rules_route_each_kind_of_question(g, question, tool, inp):
    r = answer.answer(g, question, spec.AS_OF)
    assert (r["tool"], r["input"], r["picked_by"]) == (tool, inp, "rules")
    assert r["result"] is not None


@pytest.mark.parametrize("question", ["why do we use kubernetes for the coffee machine", "What is our policy on blockchain?"])
def test_unrelated_questions_match_nothing(g, question):
    r = answer.answer(g, question, spec.AS_OF)
    assert r["tool"] is None and r["result"] is None


def test_a_model_may_only_pick_ids_the_resolvers_returned(g, monkeypatch):
    """The model picks from the tool list, but an id it invents is rejected and the rules answer instead."""
    def fake(name, inp):
        call = SimpleNamespace(type="tool_use", name=name, input=inp)
        return SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(content=[call])))
    monkeypatch.setattr(agent, "_client", lambda: fake("check_action", {"decision_id": "D99"}))
    r = answer.answer(g, "Can an agent change the Friday deploy freeze?", spec.AS_OF)
    assert r["picked_by"] == "rules" and r["input"] == {"decision_id": "D07"}
    monkeypatch.setattr(agent, "_client", lambda: fake("check_action", {"decision_id": "D07"}))
    r = answer.answer(g, "Can an agent change the Friday deploy freeze?", spec.AS_OF)
    assert r["picked_by"] == "model" and r["tool"] == "check_action" and r["result"]["gate"] in ("ALLOW", "DENY", "REVALIDATE")


def test_answers_never_write(g):
    count = lambda: g.ro_query("MATCH (n) RETURN count(n)").result_set[0][0]
    edges = lambda: g.ro_query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]
    before = (count(), edges())
    tools.start_trace()
    for q, _, _ in ROUTES:
        answer.answer(g, q, spec.AS_OF)
    trace = tools.end_trace()
    assert (count(), edges()) == before
    assert trace and not any(t["write"] for t in trace)


def test_answer_api(g, monkeypatch):
    from fastapi.testclient import TestClient
    from moot import api
    monkeypatch.setattr(api, "g", lambda: g)
    c = TestClient(api.app)
    r = c.post("/api/answer", json={"question": "Can an agent change the Friday deploy freeze?", "as_of": spec.AS_OF}).json()
    assert r["tool"] == "check_action" and r["queries"] and all(not q["write"] for q in r["queries"])
    # a follow-up names its tool and input; only read-only answer tools are accepted
    f = c.post("/api/answer", json={"question": "Who owns D01?", "tool": "decision_owner", "input": {"decision_id": "D01"}, "as_of": spec.AS_OF}).json()
    assert f["picked_by"] == "you" and f["result"]["owner"]["id"]
    assert c.post("/api/answer", json={"question": "x", "tool": "write_finding", "input": {}}).status_code == 422
    assert c.post("/api/answer", json={"question": "  "}).status_code == 422
