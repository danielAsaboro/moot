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
