"""People and teams: who knows why, what leaves with a person, bridges, single points of failure. Live FalkorDB."""
import pytest

from moot import people, tools
from moot.corpus import spec
from moot.graph import connect, seed

pytestmark = pytest.mark.integration
AS_OF = spec.AS_OF


@pytest.fixture(scope="module")
def g():
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    graph = db.select_graph("moot_test_people")
    seed(graph, fresh=True)
    yield graph
    graph.delete()


def test_who_knows_why_d01(g):
    k = people.knowers(g, "D01", AS_OF)
    by = {p["id"]: p for p in k["people"]}
    assert by["ada"]["active"] is False and {"how": "owner", "what": "D01"} in by["ada"]["roles"]  # the owner left in May
    assert any(r["what"] == "PR-412" and r["reason"] == "p_gateway_limit" for r in by["marcus"]["roles"])  # wrote the PR that killed it
    assert k["bus_factor"] == 1


def test_departure_is_computed_on_a_copy_and_matches_sole_knowers(g):
    before = tools.graph_digest(g)
    d = people.departure(g, "priya", AS_OF)
    assert [x["id"] for x in d["leaves"]] == ["D10"]
    assert [x["id"] for x in d["only_they_evidence"]] == ["p_sendgrid_free"]
    assert d["systems_nobody_else_explains"] == ["Notifications"] and d["successor"]["id"] == "kwame"
    assert tools.graph_digest(g) == before  # the company graph is never written
    assert not [n for n in connect().list_graphs() if n.startswith(g.name + "__people")]  # and the copy is gone
    sole = {p["id"]: p["sole"] for p in people.people(g, AS_OF)["people"]}
    assert sole["priya"] == ["D10"]  # WCC on the copy and the per-decision count agree


def test_someone_who_already_left_takes_nothing_more(g):
    assert people.departure(g, "ada", AS_OF)["leaves"] == []  # her knowledge already left in May
    assert people.departure(g, "nobody", AS_OF)["found"] is False


def test_people_ranking_bus_factor_and_betweenness_are_deterministic(g):
    a, b = people.people(g, AS_OF), people.people(g, AS_OF)
    assert a == b
    assert a["people"][0]["id"] == "marcus" and a["people"][0]["betweenness"] > 0
    assert a["bus_factor"]["zero"] == ["D04", "D19"]  # nobody still here wrote anything on these
    assert all(p["id"] not in ("ada", "lena") for p in a["people"])  # people who left are not ranked


def test_reason_single_points_of_failure(g):
    r = {x["id"]: x for x in people.premise_spof(g, AS_OF)["reasons"]}
    assert r["p_gateway_limit"]["why"] == "one document (PR-412)" and r["p_gateway_limit"]["decisions"] == ["D01", "D02", "D03"]
    assert r["p_infra_budget"]["why"] == "no evidence at all"


def test_people_api_and_mcp_agree(g, monkeypatch):
    from fastapi.testclient import TestClient
    from moot import api, mcp_server
    import json
    monkeypatch.setattr(api, "g", lambda: g)
    c = TestClient(api.app)
    http = c.get(f"/api/people/priya/departure?as_of={AS_OF}").json()
    http.pop("queries")
    monkeypatch.setattr(mcp_server, "_g", lambda name: g)
    assert json.loads(mcp_server.departure_impact("priya", AS_OF)) == json.loads(json.dumps(http))
    assert c.get(f"/api/decision/D01?as_of={AS_OF}").json()["knowers"]["bus_factor"] == 1
    assert c.get("/api/people/nobody/departure").status_code == 404
