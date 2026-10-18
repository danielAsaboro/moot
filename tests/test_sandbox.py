"""Post a change: the visitor's change lands in their own scratch graph, the verdicts it moves are reported, the company graph
is untouched, and Reset deletes the sandbox. Integration: needs FalkorDB."""
import pytest
from fastapi.testclient import TestClient

from moot import api, sandbox, tools
from moot.corpus import spec
from moot.graph import connect, seed

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def g():
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    graph = db.select_graph("moot_test_sandbox")
    seed(graph, fresh=True)
    yield graph
    graph.delete()


def test_a_posted_contradiction_moves_verdicts_only_in_the_sandbox(g, monkeypatch):
    monkeypatch.setattr(api, "g", lambda: g)
    before = tools.graph_digest(g)
    c = TestClient(api.app)
    # SOC 2 stops mattering: every decision that rests on it, at any depth, should move
    r = c.post(f"/api/sandbox?as_of={spec.AS_OF}", json={"premise": "p_soc2_cert", "rel": "CONTRADICTS", "at": "2026-10-01",
                                                          "title": "We no longer sell to enterprise customers"}).json()
    assert r["sandbox"].startswith(sandbox.PREFIX) and r["changed"]
    assert all(x["after"] == "MOOT" and x["before"] != "MOOT" for x in r["changed"])
    assert tools.graph_digest(g) == before  # the company graph was only read
    led = tools.ledger(connect().select_graph(r["sandbox"]), spec.AS_OF, 4)
    assert {x["id"] for x in r["changed"]} <= {x["id"] for x in led if x["verdict"] == "MOOT"}
    assert c.delete(f"/api/sandbox/{r['sandbox']}").status_code == 200
    assert r["sandbox"] not in connect().list_graphs()
    assert c.post("/api/sandbox", json={"premise": "p_nope", "rel": "CONTRADICTS"}).status_code == 422
    assert c.delete("/api/sandbox/larkspur").status_code == 404  # Reset never touches a company graph
