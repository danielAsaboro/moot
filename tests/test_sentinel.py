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
