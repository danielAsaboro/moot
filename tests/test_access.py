"""Viewer-scoped audits on the demo company: hidden evidence cannot move a verdict for that viewer, the answer counts what
was withheld, and a viewer with no permissions on file is refused. Integration: needs FalkorDB."""
import pytest

from moot import tools
from moot.graph import connect, seed

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def g():
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    graph = db.select_graph("moot_test_access")
    seed(graph, fresh=True)
    yield graph
    graph.delete()


def test_staff_see_everything(g):
    a, b = tools.audit_decision(g, "D11", "2026-10-01"), tools.audit_decision(g, "D11", "2026-10-01", viewer="staff")
    assert a["verdict"] == b["verdict"] == "DISPUTED" and b["hidden"] == 0


def test_a_hidden_chat_cannot_reaffirm_a_reason(g):
    # D11's reason was contradicted, then re-affirmed in #eng chat; a contractor does not see the chat
    a = tools.audit_decision(g, "D11", "2026-10-01", viewer="contractor")
    assert a["verdict"] == "MOOT" and a["hidden"] == 1 and all(e["kind"] != "chat" for p in a["premises"] for e in p["evidence"])


def test_an_unknown_viewer_is_refused(g):
    a = tools.audit_decision(g, "D11", "2026-10-01", viewer="stranger")
    assert not a["found"] and a["verdict"] == "NOT_PERMITTED"
