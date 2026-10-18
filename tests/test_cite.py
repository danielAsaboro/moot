"""Claim-level citations and the agent loop: a quote must be word for word in a record a tool returned, identifiers and
numbers must appear in what is cited, one repair round, and an answer with nothing supported abstains."""
import json

from moot import agentloop, cite

TEXTS = {}
cite.collect({"rows": [{"id": "pr:7", "title": "Add retry to the sync worker", "state": "merged", "link": "https://github.com/acme/x/pull/7"},
                       {"id": "msg:1", "text": "CUST-0026 reports the dashboard times out after 30 seconds", "author": "eid_1a2b3c4d"}]}, TEXTS)


def test_collect_finds_nested_records():
    assert set(TEXTS) == {"pr:7", "msg:1"} and "sync worker" in TEXTS["pr:7"]


def test_a_verbatim_quote_passes_and_an_invented_one_fails():
    ok = {"text": "PR 7 added retry to the sync worker.", "cite": [{"id": "pr:7", "quote": "Add retry to the sync worker"}]}
    bad = {"text": "PR 7 rewrote the sync worker.", "cite": [{"id": "pr:7", "quote": "Rewrite the sync worker"}]}
    ghost = {"text": "It was merged.", "cite": [{"id": "pr:9", "quote": "merged"}]}
    p = cite.check([ok, bad, ghost], TEXTS)
    assert p[0] == [] and "word for word" in p[1][0] and "not returned" in p[2][0]


def test_identifiers_and_numbers_must_be_in_the_cited_record():
    c = {"text": "CUST-0099 says it times out after 45 seconds.", "cite": [{"id": "msg:1", "quote": "the dashboard times out"}]}
    p = cite.check([c], TEXTS)[0]
    assert any("CUST-0099" in x for x in p) and any("45" in x for x in p)
    good = {"text": "CUST-0026 says the dashboard times out after 30 seconds.", "cite": [{"id": "msg:1", "quote": "the dashboard times out"}]}
    assert cite.check([good], TEXTS) == [[]]


def test_a_claim_without_citation_is_dropped_and_nothing_left_abstains():
    claims = [{"text": "The worker is fine.", "cite": []}]
    assert cite.clean(claims, cite.check(claims, TEXTS)) == []
    assert cite.render([]) == cite.ABSTAIN


def fake_chat(script):
    replies = iter(script)
    return lambda msgs: (next(replies), 10, 5, 0.01)


def test_loop_calls_tools_repairs_once_and_keeps_only_supported_claims():
    tools = {"prs": lambda a: {"rows": [{"id": "pr:7", "title": "Add retry to the sync worker", "state": "merged"}]}}
    script = ['{"tool": "prs", "args": {}}',
              json.dumps({"answer": [{"text": "PR 7 rewrote the worker.", "cite": [{"id": "pr:7", "quote": "Rewrote the worker"}]}]}),
              json.dumps({"answer": [{"text": "PR 7 added retry to the sync worker.", "cite": [{"id": "pr:7", "quote": "Add retry to the sync worker"}]}]})]
    r = agentloop.answer("What did PR 7 do?", tools, "- prs(): PRs", fake_chat(script))
    assert not r["abstained"] and r["claims"][0]["cite"][0]["id"] == "pr:7" and r["validator"]["repaired"] and r["calls"] == 1


def test_loop_abstains_with_the_fixed_line_when_nothing_holds():
    script = ['{"answer": [{"text": "It was Tuesday.", "cite": []}]}', '{"answer": [{"text": "It was Tuesday.", "cite": []}]}']
    r = agentloop.answer("When?", {}, "", fake_chat(script))
    assert r["abstained"] and r["text"].startswith(cite.ABSTAIN)


def test_a_quote_of_a_field_as_printed_and_a_link_ending_a_sentence():
    # a field quoted with its key, the way the tool printed the record, is word for word; a link at the end of a sentence
    # is the link, not the link and its full stop
    texts = {}
    cite.collect({"competitors": [{"name": "SalesMate AI", "demo": "https://x.io/demo_4", "demo_shared_by": ["eid_4350bf70"]}],
                  "issues": [{"id": "iss:1", "title": "Pipeline sync", "resolved_by": "eid_4b38019b"}]}, texts)
    claims = [{"text": "The demo of SalesMate AI was shared by eid_4350bf70.", "cite": [{"id": "SalesMate AI", "quote": '"demo_shared_by": ["eid_4350bf70"]'}]},
              {"text": "Its demo is https://x.io/demo_4.", "cite": [{"id": "SalesMate AI", "quote": "https://x.io/demo_4"}]},
              {"text": "eid_4b38019b resolved the pipeline sync issue.", "cite": [{"id": "iss:1", "quote": "resolved_by: eid_4b38019b"}]}]
    assert cite.check(claims, texts) == [[], [], []]
    bad = {"text": "The demo was shared by eid_00000000.", "cite": [{"id": "SalesMate AI", "quote": '"demo_shared_by": ["eid_00000000"]'}]}
    assert cite.check([bad], texts)[0]
