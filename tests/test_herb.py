"""HERB connector and tools on a tiny synthetic company (not HERB data): parsing, fold, policy, tools, and the guarantee that
no question text reaches the graph. The graph tests need a live FalkorDB."""
import json

import pytest

from moot import herb_tools as t
from moot.connectors import herb, herb_extract
from moot.graph import connect

SENTINEL_Q = "ZQX-QUESTION-SENTINEL what did the hidden answer say"
SENTINEL_A = "ZQX-ANSWER-SENTINEL"
P = "Widget"


def msg(mid, ts, user, text, channel):
    return {"Channel": {"name": channel, "channelID": "ch-1"}, "Message": {"User": {"userId": user, "timestamp": ts, "text": text, "utterranceID": mid}, "Reactions": []},
            "ThreadReplies": [], "id": mid}


def pr(n, title, user, state, merged, reviews, summary="", created="2026-03-01T10:00:00"):
    return {"title": title, "summary": summary or title, "link": f"https://github.com/salesforce/Widget/pull/{n}", "mergeable": "True", "merged": str(merged),
            "number": str(n), "state": state, "user": {"login": user}, "created_at": created,
            "reviews": [{"state": s, "user": {"login": u}, "comment": "ok", "submitted_at": "2026-03-02T10:00:00"} for s, u in reviews],
            "id": f"github_com_salesforce_Widget_pull_{n}"}


EMP = {e: {"employee_id": e, "name": n, "role": r, "location": "Remote", "org": "slack"} for e, n, r in [
    ("eid_00000001", "Ann Lead", "Engineering Lead"), ("eid_00000002", "Bo Dev", "Software Engineer"), ("eid_00000003", "Cy Dev", "Software Engineer"),
    ("eid_00000004", "Di Qa", "QA Specialist"), ("eid_00000005", "Ed Pm", "Product Manager"), ("eid_00000006", "Flo Ux", "UX Researcher")]}
TEAM = [{"employee_id": "eid_00000005", "name": "Ed Pm", "role": "VP of Engineering", "location": "Remote",
         "engineering_leads": [{"employee_id": "eid_00000001", "name": "Ann Lead", "role": "Engineering Lead", "location": "Remote",
                                "engineers": [{"employee_id": "eid_00000002", "name": "Bo Dev", "role": "Software Engineer"},
                                              {"employee_id": "eid_00000003", "name": "Cy Dev", "role": "Software Engineer"}]}]}]
CUSTOMERS = [{"name": "Gil Buyer", "role": "CTO", "company": "AcmeCo", "id": "CUST-0001"}, {"name": "Hal Buyer", "role": "CEO", "company": "BetaCorp", "id": "CUST-0002"}]
DOC_LINK = "https://sf-internal.slack.com/archives/docs/wgx_market_research_report"
SLACK = [
    msg("20260101-0-a0001", "2026-01-01T09:00:00", "slack_admin_bot", "@eid_00000005 created this channel on 2026-01-01 09:00:00. This is the very beginning of the planning-WGX channel.", "planning-WGX"),
    msg("20260102-0-a0002", "2026-01-02T09:00:00", "eid_00000005", f"Hi team, I've shared the <{DOC_LINK}|Market Research Report> for WGX. Feedback welcome!", "planning-WGX"),
    msg("20260102-1-a0003", "2026-01-02T09:05:00", "eid_00000006", "From a UX view, add user personas to the Target Audience section.", "planning-WGX"),
    msg("20260102-2-a0004", "2026-01-02T09:06:00", "eid_00000001", "Add latency benchmarks to the Product Features section.", "planning-WGX"),
    msg("20260102-3-a0005", "2026-01-02T09:08:00", "eid_00000005", "Thanks both, I'll add these.", "planning-WGX"),
    msg("20260103-0-a0006", "2026-01-03T09:00:00", "eid_00000002", "Hi team, I was reading about RivalPad, one of our competitors. Its weakness is slow sync.", "planning-WGX"),
    msg("20260104-0-a0007", "2026-01-04T09:00:00", "eid_00000003", "@here take a look at RivalPad—demo available here https://www.rivalpad.com/demo", "planning-WGX"),
    # bug channel: a report of two issues, a fix, a dismissal, a reopening, an unauthorised claim
    msg("20260201-0-b0001", "2026-02-01T09:00:00", "eid_00000001", "Hi team, several customers are reporting issues with Widget. Let's go through them one by one.", "bug-annlead-Widget"),
    msg("20260201-1-b0002", "2026-02-01T09:01:00", "eid_00000001", "First up, we have a 'Sync Drops Edits' issue. Edits vanish on reconnect. This affects the Sync Engine and impacts customer CUST-0001. @eid_00000002, can you take this one?", "bug-annlead-Widget"),
    msg("20260201-2-b0003", "2026-02-01T09:02:00", "eid_00000002", "Got it, on it.", "bug-annlead-Widget"),
    msg("20260201-3-b0004", "2026-02-01T09:03:00", "eid_00000001", "Thanks, @eid_00000002! Next, we have 'Slow Export Queue'. Exports take minutes. This affects the Export Module and impacts customer CUST-0002. @eid_00000003, can you handle this?", "bug-annlead-Widget"),
    msg("20260201-4-b0005", "2026-02-01T09:04:00", "eid_00000003", "Sure.", "bug-annlead-Widget"),
    msg("20260210-0-b0006", "2026-02-10T09:00:00", "eid_00000002", "Hi team, the bug titled 'Sync Drops Edits' has been resolved. You can check the approved PR here: https://github.com/salesforce/Widget/pull/9.", "bug-annlead-Widget"),
    msg("20260212-0-b0007", "2026-02-12T09:00:00", "eid_00000003", "Hi team, I looked into the reported issue about the 'Slow Export Queue'.", "bug-annlead-Widget"),
    msg("20260212-1-b0008", "2026-02-12T09:01:00", "eid_00000003", "This is expected behavior under heavy load and does not require a fix.", "bug-annlead-Widget"),
    msg("20260215-0-b0009", "2026-02-15T09:00:00", "eid_00000001", "Hi team, the 'Slow Export Queue' bug has been reopened by the customer.", "bug-annlead-Widget"),
    msg("20260216-0-b0010", "2026-02-16T09:00:00", "eid_00000004", "Hi team, the bug titled 'Sync Drops Edits' has been resolved again, I think.", "bug-annlead-Widget"),
    # develop channel: PR 1 approved and to be merged; PR 2 approved, then the team decides not to merge it
    msg("20260301-0-c0001", "2026-03-01T11:00:00", "eid_00000002", "Hi team, please check my PR for offline sync: https://github.com/salesforce/Widget/pull/1. Thoughts?", "develop-annlead-Widget"),
    msg("20260301-1-c0002", "2026-03-01T11:05:00", "eid_00000001", "LGTM, approved!", "develop-annlead-Widget"),
    msg("20260301-2-c0003", "2026-03-01T11:06:00", "eid_00000002", "Thanks! I'll merge it now.", "develop-annlead-Widget"),
    msg("20260305-0-c0004", "2026-03-05T11:00:00", "eid_00000004", "Hi team, I noticed that PR# 2 is approved but not merged yet. I heard the product direction has changed.", "develop-annlead-Widget"),
    msg("20260305-1-c0005", "2026-03-05T11:02:00", "eid_00000004", "Let's not merge it.", "develop-annlead-Widget"),
    msg("20260305-2-c0006", "2026-03-05T11:03:00", "eid_00000003", "Agreed, I'll make sure the PR is not merged.", "develop-annlead-Widget"),
]
PRODUCT = {
    "team": list(EMP), "customers": ["CUST-0001", "CUST-0002"], "slack": SLACK,
    "documents": [{"content": "WGX market research body", "date": "2026-01-02T08:00:00", "author": "eid_00000005", "type": "Market Research Report",
                   "document_link": DOC_LINK, "id": "wgx_market_research_report"}],
    "meeting_transcripts": [{"transcript": "Attendees\nAnn Lead, Bo Dev\nTranscript\nAnn Lead: Bo, you're on offline sync.\nBo Dev: I confirm.", "date": "2026-02-20T10:00:00",
                             "document_type": "product-planning", "participants": ["eid_00000001", "eid_00000002"], "id": "product_dev_Widget_1"}],
    "meeting_chats": [],
    "urls": [{"link": "https://www.rivalpad.com/demo", "description": "A demo showing how RivalPad works.", "id": "www_rivalpad_com_demo"}],
    "prs": [pr(1, "Add Offline Sync", "eid_00000002", "open", False, [("APPROVED", "eid_00000001")]),
            pr(2, "Add Sync Telemetry", "eid_00000003", "open", False, [("APPROVED", "eid_00000001")]),
            pr(3, "Add Sync Conflict Resolver", "eid_00000002", "closed", True, [("APPROVED", "eid_00000001")]),
            pr(4, "Revert PR# 3: Sync Conflict Resolver", "eid_00000002", "closed", True, [("APPROVED", "eid_00000001")],
               summary="This revert is necessary to address critical bugs introduced by PR# 3."),
            pr(9, "Fix Sync Drops Edits", "eid_00000002", "closed", True, [("APPROVED", "eid_00000001")])],
    "answerable_questions": [{"question": SENTINEL_Q, "ground_truth": SENTINEL_A, "citations": [], "type": "content"}],
    "unanswerable_questions": [{"question": SENTINEL_Q + " (unanswerable)", "ground_truth": SENTINEL_A}],
}


@pytest.fixture(scope="module")
def raw(tmp_path_factory):
    d = tmp_path_factory.mktemp("herb_raw")
    (d / "metadata").mkdir()
    (d / "products").mkdir()
    (d / "metadata" / "employee.json").write_text(json.dumps(EMP))
    (d / "metadata" / "salesforce_team.json").write_text(json.dumps(TEAM))
    (d / "metadata" / "customers_data.json").write_text(json.dumps(CUSTOMERS))
    (d / "products" / f"{P}.json").write_text(json.dumps(PRODUCT))
    return d


@pytest.fixture(scope="module")
def g(raw):
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    herb.ingest([P], graph_name="moot_test_herb", raw=raw)
    graph = db.select_graph("moot_test_herb")
    yield graph
    graph.delete()


# ---------- no graph needed ----------

def test_load_drops_question_fields(raw):
    rec = herb.load_product(raw / "products" / f"{P}.json")
    assert set(rec) == set(herb.KEEP) and "answerable_questions" not in rec
    assert SENTINEL_Q not in json.dumps(rec) and SENTINEL_A not in json.dumps(rec)


def test_heldout_refused_before_anything_is_read(tmp_path):
    for p in herb.HELDOUT:
        with pytest.raises(herb.HeldOut):
            herb.ingest([p], graph_name="never", raw=tmp_path)  # tmp_path is empty: the guard fires before any file is touched
        with pytest.raises(herb.HeldOut):
            herb.fetch(p)


def test_regex_events_and_conversation_split(raw):
    arts = herb.artifacts(P, herb.load_product(raw / "products" / f"{P}.json"))
    ev = herb.regex_events(arts)
    rep = [e for e in ev if e["type"] == "issue_reported"]
    assert [(e["issue"], e["customer"], e["person"], e["component"]) for e in rep] == [
        ("Sync Drops Edits", "CUST-0001", "eid_00000002", "Sync Engine"), ("Slow Export Queue", "CUST-0002", "eid_00000003", "Export Module")]
    assert any(e["type"] == "issue_dismissed" and e["issue"] == "Slow Export Queue" for e in ev)
    assert any(e["type"] == "pr_to_merge" and e["pr"] == 1 for e in ev)
    assert {e["speaker"] for e in ev if e["type"] == "pr_to_close"} == {"eid_00000004", "eid_00000003"}
    for e in ev:  # every quote is a literal span of its message
        assert e["quote"] in next(a["text"] for a in arts if a["id"] == e["artifact"])


def test_title_similarity():
    assert herb.token_set_ratio("Suboptimal Query Optimization", "suboptimal query optimization for the database") == 100
    assert herb.token_set_ratio("Sync Drops Edits", "Slow Export Queue") < 50


def test_model_verifier_keeps_literal_quotes_only():
    unit = [dict(id="m0", text="Hi team, the bug titled 'X' has been resolved."), dict(id="m1", text="Thanks!")]
    ok, r = herb_extract.verify(dict(type="issue_resolved", msg=1, quote="the bug titled 'X' has been   resolved"), unit)
    assert ok and r["msg"] == 0 and r["moved"]
    assert not herb_extract.verify(dict(type="issue_resolved", msg=0, quote="the bug was fixed"), unit)[0]
    assert not herb_extract.verify(dict(type="made_up", msg=0, quote="Thanks!"), unit)[0]
    assert herb_extract.parse('noise {"events": [{"type": "pr_to_merge", "msg": 0, "quote": "q", "pr": "PR#4"}]} tail')[0]["pr"] == "PR#4"


def test_fit_keeps_output_small():
    big = dict(a=[dict(x="y" * 500) for _ in range(40)], b=list(range(5)))
    out = t.fit(big)
    assert len(out) <= t.MAX_CHARS and json.loads(out)["b"] == list(range(5))


def test_tool_sets():
    assert t.SEARCH_TOOLS == ["search", "get_artifact"] and "search" in t.GRAPH_TOOLS


def test_graph_holds_no_question_text(g):
    for label in ("Evidence", "Issue", "Decision", "Person", "Project", "Customer", "Competitor"):
        rows = g.ro_query(f"MATCH (n:{label}) RETURN properties(n)").result_set
        blob = json.dumps(rows, default=str)
        assert SENTINEL_Q.split()[0] not in blob and SENTINEL_A not in blob
    rels = json.dumps(g.ro_query("MATCH ()-[r]->() RETURN properties(r)").result_set, default=str)
    assert SENTINEL_A not in rels and "ZQX-QUESTION" not in rels


def test_org_and_aliases(g):
    assert g.ro_query("MATCH (:Person {id:'eid_00000002'})-[:REPORTS_TO]->(b:Person) RETURN b.id").result_set == [["eid_00000001"]]
    assert g.ro_query("MATCH (:Customer {id:'CUST-0001'})-[:WORKS_AT]->(c:Company) RETURN c.name").result_set == [["AcmeCo"]]
    assert "WGX" in t.resolve_entity(P, name="WGX", g=g)["project"]["aliases"]


def test_issue_fold_and_policy(g):
    iss = {i["title"]: i for i in t.list_issues(P, g=g)["issues"]}
    assert iss["Sync Drops Edits"]["status"] == "resolved" and iss["Sync Drops Edits"]["resolved_by"] == "eid_00000002"
    assert iss["Slow Export Queue"]["status"] == "reopened" and iss["Slow Export Queue"]["dismissed_by"] == "eid_00000003"
    lin = t.decision_lineage(P, "Sync Drops Edits", g=g)
    assert [d["value"] for d in lin["decisions"]] == ["resolved", "reported"]
    assert lin["refused_claims"] == [] or all(c["claimed"] != "resolved" for c in lin["refused_claims"])  # same value: SUPPORTS, not a change
    lin2 = t.decision_lineage(P, "Slow Export Queue", g=g)
    assert [d["value"] for d in lin2["decisions"]] == ["reopened", "dismissed", "reported"]
    assert lin2["decisions"][1]["valid_to"] == lin2["decisions"][0]["valid_from"]  # windows chain
    assert t.rank(P, "issues_by_company", status="unresolved", g=g)["top"] == ["BetaCorp"]
    assert t.rank(P, "issues_dismissed_by", status="reopened", g=g)["top"] == ["eid_00000003"]
    assert g.ro_query("MATCH (:Issue {title:'Sync Drops Edits'})-[:FIXED_BY]->(e:Evidence) RETURN e.number").result_set == [[9]]


def test_pr_outcomes_and_refused_claim(g):
    by = {p["number"]: p for p in t._prs(g, P)}
    assert by[1]["outcome"] == "to_merge"
    assert by[2]["outcome"] == "to_close"  # the PR author agreed; the QA specialist's own claim was refused
    assert by[3]["outcome"] == "reverted_bugs" and by[4]["outcome"] == "revert"
    lin = t.decision_lineage(P, "PR 2", g=g)
    assert any(c["by"] == "eid_00000004" and c["claimed"] == "to_close" for c in lin["refused_claims"])
    assert [p["link"] for w in t.list_prs(P, topic="offline sync", status="to_merge", g=g)["workstreams"] for p in w["prs"]] == \
        ["https://github.com/salesforce/Widget/pull/1"]
    assert all(not w["workstream"].startswith("fix:") for w in t.list_prs(P, g=g)["workstreams"])  # bug fixes stay out of feature streams


def test_doc_discussion_competitors_links(g):
    d = t.doc_discussion(P, "Market Research Report", g=g)
    assert d["authors"] == ["eid_00000005"] and set(d["reviewers"]) == {"eid_00000001", "eid_00000006"}
    assert [f["by"] for f in t.doc_discussion(P, "Market Research Report", role="UX Researcher", g=g)["feedback"]] == ["eid_00000006"]
    c = t.competitors(P, g=g)["competitors"]
    assert c[0]["name"] == "RivalPad" and c[0]["demo_shared_by"] == ["eid_00000003"]
    assert c[0]["discussions"][0]["opened_by"] == "eid_00000002"
    assert [l["link"] for l in t.links_shared(P, kind="competitor_demo", g=g)["links"]] == ["https://www.rivalpad.com/demo"]


def test_tools_scoped_read_only_and_small(g):
    hits = t.search(P, "offline sync", g=g)["hits"]
    assert hits and all(h["id"].startswith(("msg:Widget", "pr:", "mtg:Widget", "doc:Widget", "url:")) for h in hits)
    conv = t.get_artifact("msg:Widget/20260305-1-c0005", g=g)
    assert [m["id"] for m in conv["conversation"]][0] == "msg:Widget/20260305-0-c0004"
    assert t.get_artifact("msg:Widget/20260305-1-c0005", product="Other", g=g)["found"] is False
    for name, args in [("list_issues", {"product": P}), ("list_prs", {"product": P}), ("competitors", {"product": P}), ("search", {"product": P, "query": "sync"}),
                       ("resolve_entity", {"product": P, "role": "Software Engineer"}), ("who_knows", {"product": P, "topic": "sync"}),
                       ("connection_path", {"product": P, "a": "eid_00000002", "b": "CUST-0001"}), ("find_missing", {"product": P, "kind": "unassigned_issues"})]:
        out = t.call(name, args, g=g)
        assert len(out) <= t.MAX_CHARS and "error" not in json.loads(out), (name, out)
    assert "error" in json.loads(t.call("list_prs", {"product": P}, allowed=t.SEARCH_TOOLS, g=g))
    n = g.ro_query("MATCH (n) RETURN count(n)").result_set[0][0]
    for name in t.GRAPH_TOOLS:
        t.call(name, {"product": P, "query": "x", "id": "x", "doc_type": "x", "metric": "issues_by_company", "subject": "x", "topic": "x", "a": "x", "b": "y", "kind": "x"}, g=g)
    assert g.ro_query("MATCH (n) RETURN count(n)").result_set[0][0] == n
