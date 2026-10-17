"""Verdict logic is pure; these run with no database."""
from moot.verdict import decision_verdict, gate, premise_state


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
    assert decision_verdict([dict(state="holds"), dict(state="unchecked")], superseded=False) == "HOLDS"


def audit(verdict, premises=(), owner_active=True, superseded_by=None):
    return dict(found=True, verdict=verdict, as_of="2026-10-16", premises=list(premises), superseded_by=superseded_by,
                owner=dict(name="Ada", active=owner_active, valid_to=None if owner_active else "2026-05-15"))


def prem(state, *events, unchecked=None):
    return dict(id="p", text="t", state=state, path=[], unchecked=unchecked, evidence=[dict(id=i, rel=r, at=a) for i, r, a in events])


def test_gate():
    assert gate(dict(found=False))["gate"] == "DENY"
    ok = gate(audit("HOLDS", [prem("holds", ("doc-1", "SUPPORTS", "2026-01-01"))]))
    assert ok["gate"] == "ALLOW" and ok["allowed"] and ok["basis"][0]["evidence"] == "doc-1"
    dead = gate(audit("MOOT", [prem("expired", ("PR-1", "CONTRADICTS", "2026-03-02"))]))
    assert dead["gate"] == "DENY" and dead["reasons"][0]["evidence"] == "PR-1" and not dead["basis"]
    assert gate(audit("DISPUTED", [prem("disputed", ("PR-1", "CONTRADICTS", "2026-01-01"), ("c-1", "SUPPORTS", "2026-02-01"))]))["gate"] == "REVALIDATE"
    assert gate(audit("HOLDS", [prem("unchecked", unchecked="no package")]))["gate"] == "REVALIDATE"
    assert gate(audit("UNDOCUMENTED"))["gate"] == "REVALIDATE"
    assert [r["code"] for r in gate(audit("HOLDS", [prem("holds")], owner_active=False))["reasons"]] == ["owner_left"]
    retired = gate(audit("RETIRED", [prem("expired", ("PR-1", "CONTRADICTS", "2026-03-02"))], superseded_by=dict(id="D09", title="x", at="2025-07-01")))
    assert retired["gate"] == "DENY" and [r["code"] for r in retired["reasons"]] == ["retired"]
