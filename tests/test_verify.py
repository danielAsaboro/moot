"""`moot verify` must pass on the committed tree and fail when a quoted number drifts. No database needed."""
from moot import verify


def test_committed_numbers_match_their_eval_output(capsys):
    assert verify.main() == 0, capsys.readouterr().out


def test_a_drifted_or_missing_claim_fails():
    c = verify.Checker()
    c.expect("doc", "| BM25 | 0.81 |", "same", r"\| BM25 \| ([\d.]+) \|", ("0.81",))
    c.expect("doc", "| BM25 | 0.79 |", "drifted", r"\| BM25 \| ([\d.]+) \|", ("0.81",))
    c.expect("doc", "BM25 scored well", "reworded", r"\| BM25 \| ([\d.]+) \|", ("0.81",))
    assert c.ok == 1 and len(c.bad) == 2 and "no match" in c.bad[1]


def test_timing_fields_are_excluded_from_the_rerun_comparison():
    a = dict(scale=[dict(n=0, graph=1.0, audit=dict(p50=1.0), samples=dict(audit=[1.0]))])
    b = dict(scale=[dict(n=0, graph=1.0, audit=dict(p50=9.0), samples=dict(audit=[9.0]))])
    assert verify.strip_timing(a) == verify.strip_timing(b)
    assert verify.strip_timing(a) != verify.strip_timing(dict(scale=[dict(n=0, graph=0.9)]))
