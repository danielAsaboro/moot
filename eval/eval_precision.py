"""Study P1: when a method flags a real decision its repository still lists as in force, did the repository later abandon it?

Flags (docs/studies.md P1): a method's first flag on a decision while it is in force. Moot's gate DENY from the backtest's
monthly replay (data/backtest/gates.json), the age rule on the third anniversary, a random flagger with Moot's budget
(200 seeds), trust the ADR (never flags). Only flags raised on or before CUT count, so each has a full three-year window.

Gold, the H1 rule (moot/heldout/gold.py), applied at the flag's date: confirmed if within three years the repository changed
the ADR's status, archived it, titled a later ADR as dropping its tool, or the tool left its dependency manifests or Terraform.

  python3 eval/eval_precision.py      -> eval/results_precision.{md,json} (needs the clones in data/backtest/.repos)
"""
from __future__ import annotations

import functools
import json
import os
import random
import statistics
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from moot.backtest.labels import REPOS_DIR  # noqa: E402
from moot.heldout import gold as G  # noqa: E402
from moot.stats import wilson  # noqa: E402

OUT = Path(os.getenv("MOOT_EVAL_OUT") or ROOT / "eval")
BT = ROOT / "data" / "backtest"
END = "2026-10-17"
CUT = "2023-10-17"  # flags after this have less than three years of future
YEARS = 3
SEEDS = 200


def plus_years(d: str, n: int) -> str:
    x = date.fromisoformat(d)
    try:
        return x.replace(year=x.year + n).isoformat()
    except ValueError:
        return x.replace(year=x.year + n, day=28).isoformat()


def end_of(d: dict) -> str:
    return min(x for x in (d["death"]["date"] if d["death"] else None, d["deleted"], END) if x)


@functools.lru_cache(maxsize=None)
def code_at(repo: str, day: str, tool: str):
    r = G.rev_at(REPOS_DIR / repo.replace("/", "__"), day)
    return G.in_code(REPOS_DIR / repo.replace("/", "__"), r, tool) if r else None


@functools.lru_cache(maxsize=None)
def grade(did: str, flag: str) -> dict:
    """The H1 rule from the flag's date: what did the repository do within three years?"""
    d = BY_ID[did]
    until = min(plus_years(flag, YEARS), END)
    events = []
    if d["death"] and flag < d["death"]["date"] <= until:
        events.append(dict(source="status", date=d["death"]["date"], what=f"{d['death']['kind']}: {d['death']['quote'][:120]}"))
    for t in d["tools"]:
        if code_at(d["repo"], flag, t) and not code_at(d["repo"], until, t):
            when = G.removal_date(REPOS_DIR / d["repo"].replace("/", "__"), t, flag, until) or until
            events.append(dict(source="code", date=when, what=f"{t} left the code"))
    first = min(events, key=lambda e: e["date"]) if events else None
    return dict(confirmed=bool(events), first=first, lead_days=(date.fromisoformat(first["date"]) - date.fromisoformat(flag)).days if first else None)


def score(flags: dict[str, str | None]) -> dict:
    fl = {k: v for k, v in flags.items() if v and v <= CUT and v <= end_of(BY_ID[k])}
    graded = {k: grade(k, v) for k, v in fl.items()}
    conf = [k for k, g in graded.items() if g["confirmed"]]
    leads = [graded[k]["lead_days"] for k in conf]
    return dict(flags=len(fl), confirmed=len(conf), precision=len(conf) / len(fl) if fl else None, precision_ci=wilson(len(conf), len(fl)),
                flags_per_death=len(fl) / len(conf) if conf else None, lead_median=statistics.median(leads) if leads else None,
                rows=[dict(id=k, flag=v, **graded[k]) for k, v in sorted(fl.items())])


def main() -> None:
    global BY_ID
    every = json.loads((BT / "decisions.json").read_text())
    gates = json.loads((BT / "gates.json").read_text())
    tool_dec = [d for d in every if d["tools"]]
    BY_ID = {d["id"]: d for d in tool_dec}
    moot = {i: next((x["as_of"] for x in s if x["gate"] == "DENY"), None) for i, s in gates.items()}
    age = {i: (plus_years(BY_ID[i]["born"], 3) if plus_years(BY_ID[i]["born"], 3) <= end_of(BY_ID[i]) else None) for i in gates}
    res = {"Moot gate (DENY)": score(moot), "age ≥ 3 years": score(age), "trust the ADR": score({i: None for i in gates})}
    budget = sum(1 for f in moot.values() if f)
    runs = []
    for k in range(SEEDS):
        rng = random.Random(1000 + k)
        pick = set(rng.sample(sorted(gates), budget))
        runs.append(score({i: (rng.choice(s)["as_of"] if i in pick else None) for i, s in gates.items()}))
    rand = dict(flags=statistics.mean(r["flags"] for r in runs), confirmed=statistics.mean(r["confirmed"] for r in runs),
                precision=statistics.mean(r["precision"] for r in runs if r["precision"] is not None))
    (OUT / "results_precision.json").write_text(json.dumps(dict(cut=CUT, years=YEARS, end=END, methods=res, random=rand), indent=1, default=str) + "\n")
    L = ["# Precision of flags on real history (study P1)", "",
         f"Every flag a method raised on one of the backtest's {len(tool_dec)} tool decisions while its repository still listed it in force, "
         f"up to {CUT} (so each has three full years of future). Graded by one rule fixed before this ran (docs/studies.md P1, the H1 rule): "
         "confirmed if within three years the repository changed the ADR's status, archived it, titled a later ADR as dropping its tool, "
         "or the tool left its dependency manifests or Terraform. Nobody on this project graded a flag.", "",
         "| method | flags | confirmed | precision (95% CI) | flags per confirmed death | median lead to the repository's own change |",
         "|---|---|---|---|---|---|"]
    for name, s in res.items():
        prec = f"{s['precision']:.2f} ({s['precision_ci'][0]:.2f}–{s['precision_ci'][1]:.2f})" if s["precision"] is not None else "–"
        L.append(f"| {'**' + name + '**' if name.startswith('Moot') else name} | {s['flags']} | {s['confirmed']} | {prec} | "
                 f"{s['flags_per_death']:.1f}" if s["flags_per_death"] else
                 f"| {'**' + name + '**' if name.startswith('Moot') else name} | {s['flags']} | {s['confirmed']} | {prec} | –")
        L[-1] += f" | {s['lead_median']:.0f} days |" if s["lead_median"] is not None else " | – |"
    L.append(f"| random, Moot's budget (mean of {SEEDS}) | {rand['flags']:.1f} | {rand['confirmed']:.1f} | {rand['precision']:.2f} | – | – |")
    L += ["", "## Every Moot flag and what the repository did", "", "| decision | flagged | confirmed | what happened, and when |", "|---|---|---|---|"]
    for r in res["Moot gate (DENY)"]["rows"]:
        L.append(f"| {r['id']} | {r['flag']} | {'yes' if r['confirmed'] else 'no'} | {r['first']['what'] + ' (' + r['first']['date'] + ')' if r['first'] else ''} |")
    (OUT / "results_precision.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:12]))


BY_ID: dict = {}

if __name__ == "__main__":
    main()
