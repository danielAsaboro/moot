"""Freeze the head-to-head question set and its labels (study S3 in docs/studies.md), before any arm runs.

Labels come from data/truth.json alone, through a verdict rule written here independently of moot/verdict.py and
without FalkorDB: a decision's verdict on a date, the documents that killed its reason, and the date its current
verdict began. Three questions per decision and date, asked of every arm:

  holds   does decision X still hold as of T?      -> HOLDS | MOOT | DISPUTED | UNDOCUMENTED | RETIRED | NOT_YET
  why     which documents decided that?            -> scored on MOOT/DISPUTED: at least one invalidating document cited
  since   since when has that been the verdict?    -> scored on MOOT/DISPUTED/RETIRED: the exact date

Dates: the spec date (truth.json as_of) and two time-travel dates, 2025-06-01 and 2026-01-01. Writes eval/baseline/questions.json and
prints its sha256, which docs/studies.md S3 records.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "baseline" / "questions.json"
TRAVEL = ("2025-06-01", "2026-01-01")


def closure(truth: dict, pids: list[str]) -> set[str]:
    by = {p["id"]: p for p in truth["premises"]}
    out, todo = set(), list(pids)
    while todo:
        p = todo.pop()
        if p in out:
            continue
        out.add(p)
        if by[p].get("derived_from"):
            todo.append(by[p]["derived_from"])
    return out


def premise_at(events: list[dict], t: str) -> str:
    ev = sorted((e for e in events if e["date"] <= t), key=lambda e: (e["date"], e["rel"] == "SUPPORTS"))
    if ev and ev[-1]["rel"] == "CONTRADICTS":
        return "expired"
    if any(e["rel"] == "CONTRADICTS" for e in ev):
        return "disputed"
    return "ok"


def verdict_at(truth: dict, d: dict, t: str) -> str:
    if d["decided_on"] > t:
        return "NOT_YET"
    succ = [x for x in truth["decisions"] if d["id"] in (x.get("supersedes") or []) and x["decided_on"] <= t]
    if succ:
        return "RETIRED"
    if not d["premises"]:
        return "UNDOCUMENTED"
    states = {premise_at([e for e in truth["evidence"] if e["premise"] == p], t) for p in closure(truth, d["premises"])}
    return "MOOT" if "expired" in states else "DISPUTED" if "disputed" in states else "HOLDS"


def change_dates(truth: dict, d: dict) -> list[str]:
    ps = closure(truth, d["premises"])
    dates = {d["decided_on"]} | {e["date"] for e in truth["evidence"] if e["premise"] in ps}
    dates |= {x["decided_on"] for x in truth["decisions"] if d["id"] in (x.get("supersedes") or [])}
    return sorted(dates)


def since(truth: dict, d: dict, t: str) -> str | None:
    """The first day of the final run of the verdict it has on t."""
    v = verdict_at(truth, d, t)
    start = None
    for x in [x for x in change_dates(truth, d) if x <= t]:
        if verdict_at(truth, d, x) == v:
            start = start or x
        else:
            start = None
    return start


def invalidating(truth: dict, d: dict, t: str) -> list[str]:
    ps = closure(truth, d["premises"])
    return sorted(e["id"] for e in truth["evidence"] if e["premise"] in ps and e["rel"] == "CONTRADICTS" and e["date"] <= t)


def main() -> None:
    truth = json.loads((ROOT / "data" / "truth.json").read_text())
    qs = []
    for t in (truth["as_of"], *TRAVEL):
        for d in truth["decisions"]:
            v = verdict_at(truth, d, t)
            qs.append(dict(id=f"{d['id']}@{t}", decision_id=d["id"], title=d["title"], as_of=t,
                           question=f"As of {t}, does the decision \"{d['title']}\" still hold? If not, which documents show it, and since when?",
                           label=dict(verdict=v, invalidating=invalidating(truth, d, t) if v in ("MOOT", "DISPUTED") else [],
                                      since=since(truth, d, t) if v in ("MOOT", "DISPUTED", "RETIRED") else None)))
    # sanity: on the spec date the independent rule must reproduce the spec's own expected verdicts
    exp = {d["id"]: d["expected"] for d in truth["decisions"]}
    bad = [q["decision_id"] for q in qs if q["as_of"] == truth["as_of"] and q["label"]["verdict"] != exp[q["decision_id"]]]
    assert not bad, f"label rule disagrees with truth.json expected on {bad}"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(dict(frozen_from="data/truth.json", dates=[truth["as_of"], *TRAVEL], questions=qs), indent=1) + "\n"
    OUT.write_text(body)
    from collections import Counter
    print(Counter((q["as_of"], q["label"]["verdict"]) for q in qs))
    print("sha256", hashlib.sha256(body.encode()).hexdigest())


if __name__ == "__main__":
    main()
