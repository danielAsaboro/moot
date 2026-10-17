"""Deterministic verdicts. No model is involved: rows in, verdict out."""
from __future__ import annotations

HOLDS, MOOT, DISPUTED, UNDOCUMENTED, RETIRED = "HOLDS", "MOOT", "DISPUTED", "UNDOCUMENTED", "RETIRED"


def premise_state(events: list[dict]) -> str:
    """events: [{rel: SUPPORTS|CONTRADICTS, at: 'YYYY-MM-DD', ...}] already filtered to <= as_of.

    expired   the latest dated event contradicts the premise
    disputed  the premise was contradicted and later re-affirmed
    holds     no contradiction on record
    """
    if not events:
        return "holds"
    ordered = sorted(events, key=lambda e: (e["at"], e["rel"] == "SUPPORTS"))
    if ordered[-1]["rel"] == "CONTRADICTS":
        return "expired"
    if any(e["rel"] == "CONTRADICTS" for e in ordered):
        return "disputed"
    return "holds"


def decision_verdict(premises: list[dict], superseded: bool) -> str:
    """premises: [{state: holds|expired|disputed|unchecked}]. An unchecked premise does not change the verdict; the gate blocks on it."""
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


def gate(audit: dict) -> dict:
    """May an agent act on this decision? Pure: the audit rows in, ALLOW | DENY | REVALIDATE out.

    DENY        the graph shows the decision is gone: not in the graph, not yet made, retired, or a premise is contradicted
    REVALIDATE  the graph cannot vouch for it: no premise recorded, a premise disputed or never checked, or the owner has left
    ALLOW       every premise holds at the audited depth and nothing above applies; `basis` is the evidence that says so
    """
    if not audit.get("found"):
        return dict(gate=DENY, allowed=False, verdict="NOT_IN_GRAPH", basis=[],
                    reasons=[dict(code="not_in_graph", text="The decision is not in the graph, so nothing vouches for it.")])
    v, reasons, basis = audit["verdict"], [], []
    if v == "NOT_YET":
        reasons.append(dict(code="not_yet", text=f"Not decided yet as of {audit['as_of']}."))
    elif v == RETIRED:
        s = audit["superseded_by"]
        reasons.append(dict(code="retired", text=f"Retired on {s['at']} by {s['id']} ({s['title']}).", evidence=s["id"]))
    elif v == UNDOCUMENTED:
        reasons.append(dict(code="undocumented", text="No premise is recorded, so there is nothing to check it against."))
    # a retired decision is not audited as if it were still in force: its premises no longer bear on any action
    for p in ([] if v in ("NOT_YET", RETIRED) else audit.get("premises", [])):
        ev = sorted(p["evidence"], key=lambda e: e["at"])
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
        else:
            sup = [e for e in ev if e["rel"] == "SUPPORTS"]
            basis.append(dict(premise=p["id"], text=p["text"], path=p["path"], evidence=sup[-1]["id"] if sup else None,
                              at=sup[-1]["at"] if sup else None))
    owner = audit.get("owner")
    if v not in ("NOT_YET", RETIRED) and owner and not owner["active"]:
        reasons.append(dict(code="owner_left", text=f"The owner of record, {owner['name']}, left on {owner['valid_to']}; nobody is accountable for it."))
    g = DENY if any(r["code"] in BLOCKING for r in reasons) else REVALIDATE if reasons else ALLOW
    return dict(gate=g, allowed=g == ALLOW, verdict=v, reasons=reasons, basis=basis if g == ALLOW else [])
