"""The extractor's write guards are pure and run without a model."""
from moot.ingest import extract

DOC = dict(id="PR-1", text="Raises the gateway limit to 100 MB. The new limit applies from 2026-04-01.", kind="pr", date="2026-03-02")
IDS = {"p_gateway_limit"}


def rel(**kw):
    return dict(dict(premise_id="p_gateway_limit", rel="CONTRADICTS", quote="Raises the gateway limit to 100 MB.", reason="the limit moved"), **kw)


def test_schema_errors_earn_a_re_ask():
    assert extract.schema_errors({"relations": [rel()]}) == []
    assert extract.schema_errors({}) and extract.schema_errors([])
    errs = extract.schema_errors({"relations": [rel(rel="MAYBE", reason=""), rel(effective_on="April")]})
    assert len(errs) == 3


def test_ids_are_copied_never_repaired_and_quotes_must_be_verbatim():
    kept, dropped = extract.validate_relations(
        [rel(), rel(premise_id="p_gateway_limitt"), rel(quote="raises the limit"), rel(effective_on="2026-04-01", effective_quote="not in the doc")],
        DOC, IDS)
    assert len(kept) == 1
    assert [d["dropped"] for d in dropped] == ["unknown premise id 'p_gateway_limitt'", "quote is not in the document",
                                               "effective_on given without a quote from the document"]


def test_an_effective_date_with_its_quote_is_kept():
    kept, _ = extract.validate_relations([rel(effective_on="2026-04-01", effective_quote="The new limit applies from 2026-04-01.")], DOC, IDS)
    assert kept[0]["effective_on"] == "2026-04-01"


class FakeClient:
    """Replays canned replies so the re-ask loop can be tested without a model."""
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw["messages"])
        text = self.replies.pop(0)
        return type("R", (), {"content": [type("B", (), {"type": "text", "text": text})()]})()


def test_a_reply_that_fails_twice_keeps_nothing():
    log = []
    c = FakeClient(['{"relations": [{"premise_id": "p_gateway_limit"}]}', "not json"])
    assert extract.extract_evidence(c, DOC, [dict(id="p_gateway_limit", text="limit")], log) == []
    assert "Your reply failed validation" in c.calls[1][-1]["content"] and log[0]["dropped"].startswith("schema failed")


def test_a_corrected_reply_is_kept():
    import json
    c = FakeClient(['{"relations": [{"premise_id": "p_gateway_limit"}]}', json.dumps({"relations": [rel()]})])
    assert [r["premise_id"] for r in extract.extract_evidence(c, DOC, [dict(id="p_gateway_limit", text="limit")])] == ["p_gateway_limit"]
