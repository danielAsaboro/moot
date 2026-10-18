"""Verdict logic is pure; these run with no database."""
from moot.verdict import decision_verdict, gate, premise_state


def ev(*pairs):
    return [dict(rel=r, at=a) for r, a in pairs]


def test_premise_states():
    assert premise_state([]) == "unevidenced"   # nothing either way is not "holds"
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
    assert [r["code"] for r in gate(audit("HOLDS", [prem("holds", ("doc-1", "SUPPORTS", "2026-01-01"))], owner_active=False))["reasons"]] == ["owner_left"]
    retired = gate(audit("RETIRED", [prem("expired", ("PR-1", "CONTRADICTS", "2026-03-02"))], superseded_by=dict(id="D09", title="x", at="2025-07-01")))
    assert retired["gate"] == "DENY" and [r["code"] for r in retired["reasons"]] == ["retired"]


def test_unevidenced_premise_revalidates_but_keeps_the_verdict():
    assert decision_verdict([dict(state="holds"), dict(state="unevidenced")], superseded=False) == "HOLDS"
    r = gate(audit("HOLDS", [prem("holds", ("doc-1", "SUPPORTS", "2026-01-01")), prem("unevidenced")]))
    assert r["gate"] == "REVALIDATE" and [x["code"] for x in r["reasons"]] == ["premise_unevidenced"] and r["basis"] == []


def test_blocking_reasons_come_first():
    r = gate(audit("MOOT", [prem("unevidenced"), prem("expired", ("PR-1", "CONTRADICTS", "2026-03-02"))], owner_active=False))
    assert [x["code"] for x in r["reasons"]] == ["premise_expired", "premise_unevidenced", "owner_left"]


def test_coverage_refuses_an_empty_read():
    ok = audit("HOLDS", [prem("holds", ("doc-1", "SUPPORTS", "2026-01-01"))])
    assert gate(ok, dict(decisions=30, evidence_edges=50))["gate"] == "ALLOW"
    assert gate(ok, dict(decisions=0, evidence_edges=0))["reasons"][0]["code"] == "graph_empty"
    none = gate(ok, dict(decisions=30, evidence_edges=0))
    assert none["gate"] == "REVALIDATE" and none["reasons"][0]["code"] == "graph_has_no_evidence"


def test_owner_ruling_settles_what_came_before():
    disputed = ev(("CONTRADICTS", "2026-01-01"), ("SUPPORTS", "2026-02-01"))
    assert premise_state(disputed) == "disputed"
    ruled = disputed + [dict(rel="SUPPORTS", at="2026-03-01", kind="ruling")]
    assert premise_state(ruled) == "holds"
    assert premise_state([dict(rel="SUPPORTS", at="2026-03-01", kind="ruling")]) == "holds"   # an unevidenced premise, ruled on
    assert premise_state(ruled + ev(("CONTRADICTS", "2026-04-01"))) == "expired"              # newer evidence reopens it
    assert premise_state(ruled + ev(("CONTRADICTS", "2026-04-01"), ("SUPPORTS", "2026-05-01"))) == "disputed"
    assert premise_state(disputed + [dict(rel="CONTRADICTS", at="2026-03-01", kind="ruling")]) == "expired"
    # same day: the ruling sorts after the evidence it rules on
    assert premise_state([dict(rel="SUPPORTS", at="2026-01-01", kind="ruling")] + ev(("CONTRADICTS", "2026-01-01"))) == "holds"


def test_effective_date_orders_and_statement_date_breaks_ties():
    # stated later, effective earlier: the effective date decides the order
    late_news = [dict(rel="SUPPORTS", at="2026-02-01"), dict(rel="CONTRADICTS", at="2026-01-15", stated="2026-03-01")]
    assert premise_state(late_news) == "disputed"
    same_day = [dict(rel="CONTRADICTS", at="2026-01-01", stated="2026-01-05"), dict(rel="SUPPORTS", at="2026-01-01", stated="2026-01-02")]
    assert premise_state(same_day) == "expired"
