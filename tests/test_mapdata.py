"""The map view's export: the whole network with month-by-month verdicts and reason states. Integration tests against a
live FalkorDB (skipped when none is reachable), on their own tenant graph."""
import pytest

from moot import mapdata, tools
from moot.corpus import spec
from moot.graph import connect, seed

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def g():
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    graph = db.select_graph("moot_test_map")
    seed(graph, fresh=True)
    yield graph
    graph.delete()


@pytest.fixture(scope="module")
def data(g):
    return mapdata.export(g, spec.AS_OF)


def test_month_ends_run_to_the_as_of_date():
    assert mapdata.month_ends("2025-03-10") == ["2025-01-31", "2025-02-28", "2025-03-10"]
    assert mapdata.month_ends("2025-01-31") == ["2025-01-31"]


def test_the_last_month_matches_the_ledger(g, data):
    assert data["months"][-1] == spec.AS_OF
    today = {r["id"]: r["verdict"] for r in tools.ledger(g, spec.AS_OF, 4)}
    assert {d: v[-1] for d, v in data["verdicts"].items()} == today
    assert set(data["paths"]) == set(today) == set(data["gate"])


def test_states_change_only_with_dated_evidence(data):
    """D01 rests on the gateway limit; PR-412 contradicted it on 2026-03-02, so it was not moot before March 2026."""
    months, gate_limit, d01 = data["months"], data["premise_state"]["p_gateway_limit"], data["verdicts"]["D01"]
    for i, m in enumerate(months):
        if m < "2026-03-02":
            assert gate_limit[i] != "expired" and d01[i] != "MOOT"
    assert gate_limit[-1] == "expired" and d01[-1] == "MOOT"
    assert any(e["src"] == "PR-412" and e["rel"] == "CONTRADICTS" and e["dst"] == "p_gateway_limit" for e in data["edges"])


def test_a_decision_has_no_verdict_before_it_was_made(data):
    decided = {n["id"]: n["decided_on"] for n in data["nodes"] if n["label"] == "Decision"}
    for d, row in data["verdicts"].items():
        for m, v in zip(data["months"], row):
            assert (v is None) == (m < decided[d])


def test_the_export_never_writes(g):
    count = lambda: (g.ro_query("MATCH (n) RETURN count(n)").result_set[0][0], g.ro_query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0])
    before = count()
    tools.start_trace()
    mapdata.export(g, "2025-06-30")
    trace = tools.end_trace()
    assert count() == before
    assert trace and not any(t["write"] for t in trace)


def test_api_route(g, monkeypatch):
    from fastapi.testclient import TestClient
    from moot import api
    monkeypatch.setattr(api, "g", lambda: g)
    c = TestClient(api.app)
    r = c.get("/api/map", params={"as_of": spec.AS_OF, "depth": 4})
    assert r.status_code == 200 and r.json()["as_of"] == spec.AS_OF and r.json()["queries"]
    assert c.get("/api/map", params={"as_of": "last tuesday"}).status_code == 422
    assert c.get("/api/map", params={"depth": 9}).status_code == 422
