"""Slack and issue exports: files on disk become dated chat and ticket evidence that MENTIONS the decisions they name,
merged into an existing graph without changing any verdict. Integration: needs FalkorDB."""
import json

import pytest

from moot import tools
from moot.connectors import exports
from moot.graph import connect, seed

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def g():
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    graph = db.select_graph("moot_test_exports")
    seed(graph, fresh=True)
    yield graph
    graph.delete()


def slack_dir(tmp):
    (tmp / "eng").mkdir()
    (tmp / "users.json").write_text(json.dumps([{"id": "U1", "name": "ada", "real_name": "Ada Okafor"}]))
    (tmp / "channels.json").write_text(json.dumps([{"name": "eng"}]))
    (tmp / "eng" / "2026-03-02.json").write_text(json.dumps([
        {"type": "message", "user": "U1", "text": "Do we still need D01? The upload cap looks wrong now.", "ts": "1772409600.000100"},
        {"type": "message", "user": "U1", "text": "Agreed, re-open it.", "ts": "1772409700.000200", "thread_ts": "1772409600.000100"},
        {"type": "message", "subtype": "channel_join", "user": "U1", "text": "joined", "ts": "1772409800.0"}]))
    return tmp


def test_slack_export_becomes_dated_chat_that_mentions_the_decision(g, tmp_path):
    before = tools.audit_decision(g, "D01", "2026-10-01")["verdict"]
    p = exports.slack(slack_dir(tmp_path), exports.decision_index(g))
    assert len([n for n in p["nodes"] if n["label"] == "Evidence"]) == 2  # the join is skipped
    r = exports.merge(g, p, tmp_path / "out.json")
    assert r["mentions"] == 1 and r["decisions_mentioned"] == 1
    d = tools.discussions(g, "D01")
    assert d["items"][0]["kind"] == "chat" and d["items"][0]["date"] == "2026-03-02" and d["items"][0]["authors"] == ["Ada Okafor"]
    assert tools.audit_decision(g, "D01", "2026-10-01")["verdict"] == before  # a mention never moves a verdict


def test_github_and_jira_issue_exports(g, tmp_path):
    gh = tmp_path / "issues.json"
    gh.write_text(json.dumps([{"number": 9, "title": "Revisit D17", "state": "OPEN", "author": {"login": "marcus"},
                               "createdAt": "2026-04-01T10:00:00Z", "closedAt": None, "body": "D17 blocks the EU launch", "url": "u"}]))
    jira = tmp_path / "jira.json"
    jira.write_text(json.dumps({"issues": [{"key": "OPS-4", "fields": {"summary": "D17 audit", "status": {"name": "Done"},
                                "reporter": {"displayName": "Kwame Boateng"}, "created": "2026-05-01T09:00:00.000+0000",
                                "resolutiondate": "2026-05-03T09:00:00.000+0000", "description": "closed"}}]}))
    idx = exports.decision_index(g)
    exports.merge(g, exports.issues(gh, idx, "acme/app"), tmp_path / "a.json")
    exports.merge(g, exports.issues(jira, idx), tmp_path / "b.json")
    items = {i["id"]: i for i in tools.discussions(g, "D17")["items"]}
    assert items["issue:acme/app#9"]["kind"] == "ticket" and items["jira:OPS-4"]["state"] == "Done"
    assert tools.discussions(g, "D17", as_of="2026-04-15")["items"][0]["id"] == "issue:acme/app#9"  # dated: OPS-4 not yet
