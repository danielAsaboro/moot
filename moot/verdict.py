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
    """premises: [{state: holds|expired|disputed}]"""
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
