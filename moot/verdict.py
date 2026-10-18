"""Deterministic verdicts. No model is involved: rows in, verdict out."""
from __future__ import annotations

HOLDS, MOOT, DISPUTED, UNDOCUMENTED, RETIRED = "HOLDS", "MOOT", "DISPUTED", "UNDOCUMENTED", "RETIRED"


def event_order(e: dict) -> tuple:
    """Order by the date a change took effect (`at`), then by the date it was stated (`stated`, defaults to `at`).
    On the same day an affirmation sorts after a contradiction, and an owner's ruling after both: the ruler saw them."""
    return (e["at"], e.get("stated") or e["at"], e["rel"] == "SUPPORTS", e.get("kind") == "ruling")


def premise_state(events: list[dict]) -> str:
    """events: [{rel: SUPPORTS|CONTRADICTS, at: 'YYYY-MM-DD', stated?: 'YYYY-MM-DD', kind?: 'ruling'}] already filtered to
    what was known on as_of.

    expired      the latest dated event contradicts the premise
    disputed     the premise was contradicted and later re-affirmed
    holds        the premise has dated support and no standing contradiction
    unevidenced  nothing on record either way: nobody ever checked it, so "no contradiction" is not "holds"

    An owner's ruling (kind='ruling', a Finding written after approval) settles everything before it: only the ruling and
    later events count. Newer evidence after the ruling reopens the question by the same rules.
    """
    if not events:
        return "unevidenced"
    ordered = sorted(events, key=event_order)
    rulings = [i for i, e in enumerate(ordered) if e.get("kind") == "ruling"]
    if rulings:
        ordered = ordered[rulings[-1]:]
    if ordered[-1]["rel"] == "CONTRADICTS":
        return "expired"
    if any(e["rel"] == "CONTRADICTS" for e in ordered):
        return "disputed"
    return "holds"


def decision_verdict(premises: list[dict], superseded: bool) -> str:
    """premises: [{state: holds|expired|disputed|unchecked|unevidenced}]. An unchecked or unevidenced premise does not change
    the verdict (nothing contradicts it); the gate blocks on it."""
    if superseded:
        return RETIRED
    if not premises:
        return UNDOCUMENTED
    states = {p["state"] for p in premises}
    if "expired" in states:
        return MOOT
    if "disputed" in states:
        return DISPUTED
    return HOLDS


ALLOW, DENY, REVALIDATE = "ALLOW", "DENY", "REVALIDATE"
BLOCKING = {"not_in_graph", "not_yet", "retired", "premise_expired"}


def gate(audit: dict, coverage: dict | None = None) -> dict:
    """May an agent act on this decision? Pure: the audit rows in, ALLOW | DENY | REVALIDATE out.

    DENY        the graph shows the decision is gone: not in the graph, not yet made, retired, or a premise is contradicted
    REVALIDATE  the graph cannot vouch for it: no premise recorded, a premise disputed, never checked or never evidenced,
                the owner has left, or the graph holds no evidence at all
    ALLOW       every premise has dated support at the audited depth and nothing above applies; `basis` is that evidence

    coverage: {decisions, evidence_edges} for the whole graph. An empty read is not a negative: a graph with no decisions
    or no dated evidence cannot vouch for anything, whatever the rule would say.
    """
    if coverage is not None and not coverage.get("decisions"):
        return dict(gate=DENY, allowed=False, verdict="NOT_IN_GRAPH", basis=[],
                    reasons=[dict(code="graph_empty", text="The graph holds no decisions, so it cannot vouch for any.")])
    if not audit.get("found"):
        return dict(gate=DENY, allowed=False, verdict="NOT_IN_GRAPH", basis=[],
                    reasons=[dict(code="not_in_graph", text="The decision is not in the graph, so nothing vouches for it.")])
    v, reasons, basis = audit["verdict"], [], []
    if coverage is not None and not coverage.get("evidence_edges"):
        reasons.append(dict(code="graph_has_no_evidence", text="The graph holds decisions but no dated evidence, so no premise was ever checked."))
    if v == "NOT_YET":
        reasons.append(dict(code="not_yet", text=f"Not decided yet as of {audit['as_of']}."))
    elif v == RETIRED:
        s = audit["superseded_by"]
        reasons.append(dict(code="retired", text=f"Retired on {s['at']} by {s['id']} ({s['title']}).", evidence=s["id"]))
    elif v == UNDOCUMENTED:
        reasons.append(dict(code="undocumented", text="No premise is recorded, so there is nothing to check it against."))
    # a retired decision is not audited as if it were still in force: its premises no longer bear on any action
    for p in ([] if v in ("NOT_YET", RETIRED) else audit.get("premises", [])):
        ev = sorted(p["evidence"], key=event_order)
        if p["state"] == "expired":
            c = [e for e in ev if e["rel"] == "CONTRADICTS"][-1]
            reasons.append(dict(code="premise_expired", text=f"\"{p['text']}\" was contradicted on {c['at']} by {c['id']}.",
                                premise=p["id"], evidence=c["id"], path=p["path"]))
        elif p["state"] == "disputed":
            c = [e for e in ev if e["rel"] == "CONTRADICTS"][-1]
            s = [e for e in ev if e["rel"] == "SUPPORTS"][-1]
            reasons.append(dict(code="premise_disputed", text=f"\"{p['text']}\" was contradicted by {c['id']} and re-affirmed by {s['id']}; the owner has to rule.",
                                premise=p["id"], evidence=c["id"], path=p["path"]))
        elif p["state"] == "unchecked":
            reasons.append(dict(code="premise_unchecked", text=f"\"{p['text']}\" could not be checked: {p.get('unchecked')}.",
                                premise=p["id"], path=p["path"]))
        elif p["state"] == "unevidenced":
            reasons.append(dict(code="premise_unevidenced", text=f"\"{p['text']}\" has no dated evidence either way; nobody has checked it.",
                                premise=p["id"], path=p["path"]))
        else:
            sup = [e for e in ev if e["rel"] == "SUPPORTS"]
            basis.append(dict(premise=p["id"], text=p["text"], path=p["path"], evidence=sup[-1]["id"] if sup else None,
                              at=sup[-1]["at"] if sup else None, ruling=bool(sup) and sup[-1].get("kind") == "ruling"))
    owner = audit.get("owner")
    if v not in ("NOT_YET", RETIRED) and owner and not owner["active"]:
        reasons.append(dict(code="owner_left", text=f"The owner of record, {owner['name']}, left on {owner['valid_to']}; nobody is accountable for it."))
    reasons.sort(key=lambda r: r["code"] not in BLOCKING)  # what denies comes first; stable within each group
    g = DENY if any(r["code"] in BLOCKING for r in reasons) else REVALIDATE if reasons else ALLOW
    return dict(gate=g, allowed=g == ALLOW, verdict=v, reasons=reasons, basis=basis if g == ALLOW else [])
