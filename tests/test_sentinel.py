"""The sentinel on the demo company: a reason that broke is a regression with its blast radius and a draft memo that waits
for approval; a supersession by someone without standing is flagged; plain evidence needs no standing. Integration."""
import pytest

from moot import sentinel
from moot.graph import connect, seed

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def g():
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    graph = db.select_graph("moot_test_sentinel")
    seed(graph, fresh=True)
    yield graph
    graph.delete()


def test_a_broken_reason_is_a_regression_with_blast_radius_and_a_draft(g):
    r = sentinel.scan(g, "2025-06-01", "2026-10-01")
    d01 = next(a for a in r["alerts"] if a["decision"] == "D01")
    assert d01["kind"] == "regression" and d01["before"] == "HOLDS" and d01["after"] == "MOOT"
    assert any(e["id"] == "PR-412" and e["rel"] == "CONTRADICTS" and e["authorised"] is None for e in d01["events"])
    assert {"D02", "D03"} <= set(d01["blast_radius"]) and d01["draft"]["needs_approval"] and d01["draft"]["text"]


def test_a_supersession_without_standing_is_flagged(g):
    r = sentinel.scan(g, "2025-06-01", "2026-10-01")
    d28 = next(a for a in r["alerts"] if a["decision"] == "D28")
    e = d28["events"][0]
    assert d28["kind"] == "retired" and e["rel"] == "SUPERSEDES" and e["author"] == "Ada Okafor" and e["authorised"] is False


def test_nothing_changes_in_an_empty_window(g):
    assert sentinel.scan(g, "2026-10-01", "2026-10-01")["alerts"] == []


def test_neighbourhood_and_paths_respect_the_date(g):
    from moot import tools
    now = tools.path_between(g, "D01", "marcus", "2026-10-01")
    assert now["found"] and all(e["at"] <= "2026-10-01" for p in now["paths"] for e in p["edges"])
    # Kwame only became anyone's manager on 2025-08-01: before that no path runs through him
    early = tools.path_between(g, "D01", "marcus", "2025-07-01")
    assert all("kwame" not in [n["id"] for n in p["nodes"]] for p in early.get("paths", []))
    edges = tools.neighbourhood(g, "marcus", "2026-10-01")["edges"]
    assert {"rel": "REPORTS_TO", "id": "kwame"}.items() <= next(e for e in edges if e["id"] == "kwame").items()
