"""The product gate policy ("warn"): deny only what the graph shows is gone, let the rest through with warnings and who to
ask. The strict rule (REVALIDATE) stays available and is what every registered study was scored with."""
import pytest

from moot import tools
from moot.corpus import spec
from moot.graph import connect, seed
from moot.verdict import gate

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def g():
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    graph = db.select_graph("moot_test_gate_policy")
    seed(graph, fresh=True)
    yield graph
    graph.delete()


def test_warn_denies_only_what_is_gone_and_allows_the_rest_with_warnings(g):
    for did, strict, warn in (("D01", "DENY", "DENY"), ("D28", "DENY", "DENY"),   # a dead reason; retired
                              ("D06", "REVALIDATE", "ALLOW"), ("D05", "REVALIDATE", "ALLOW"), ("D04", "REVALIDATE", "ALLOW")):
        s = tools.check_action(g, did, spec.AS_OF, policy="strict")
        w = tools.check_action(g, did, spec.AS_OF, policy="warn")
        assert (s["gate"], w["gate"]) == (strict, warn), did
        if warn == "ALLOW":
            assert not w["verified"] and w["warnings"] and w["route"]["why"]  # unverified: the warning goes to who to ask


def test_no_decision_the_strict_gate_denies_is_allowed_by_warn(g):
    for r in tools.ledger(g, spec.AS_OF, 4):
        if tools.check_action(g, r["id"], spec.AS_OF, policy="strict")["gate"] == "DENY":
            assert tools.check_action(g, r["id"], spec.AS_OF, policy="warn")["gate"] == "DENY", r["id"]


def test_an_empty_graph_still_denies():
    out = gate(dict(found=True, verdict="HOLDS", premises=[], owner=None), dict(decisions=0, evidence_edges=0), policy="warn")
    assert out["gate"] == "DENY"
