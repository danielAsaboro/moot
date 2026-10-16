"""Verdict logic is pure; these run with no database."""
from moot.verdict import decision_verdict, premise_state


def ev(*pairs):
    return [dict(rel=r, at=a) for r, a in pairs]


def test_premise_states():
    assert premise_state([]) == "holds"
    assert premise_state(ev(("SUPPORTS", "2026-01-01"))) == "holds"
    assert premise_state(ev(("CONTRADICTS", "2026-01-01"))) == "expired"
    assert premise_state(ev(("CONTRADICTS", "2026-01-01"), ("SUPPORTS", "2026-02-01"))) == "disputed"
    assert premise_state(ev(("SUPPORTS", "2026-01-01"), ("CONTRADICTS", "2026-02-01"))) == "expired"


def test_decision_verdicts():
    assert decision_verdict([], superseded=False) == "UNDOCUMENTED"
    assert decision_verdict([dict(state="holds")], superseded=True) == "RETIRED"
    assert decision_verdict([dict(state="holds"), dict(state="expired")], superseded=False) == "MOOT"
    assert decision_verdict([dict(state="holds"), dict(state="disputed")], superseded=False) == "DISPUTED"
    assert decision_verdict([dict(state="holds")], superseded=False) == "HOLDS"
