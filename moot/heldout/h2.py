"""Study H2 (docs/studies.md): a fresh held-out set from repositories outside the backtest and H1, built by H1's own code.

  python3 -m moot.heldout.h2 mine      clone and parse the H2 repositories -> data/h2/raw.json
  python3 -m moot.heldout.h2 label     tag tools, label with the H1 rule at T0 = 2022-10-17 / END = 2025-10-17, split, hash
                                       -> eval/h2/gold.json (then pin its sha256 in eval/h2/GOLD.sha256 and commit, before any arm)
  python3 -m moot.heldout.h2 evidence  maintenance and licence evidence for any catalogue tool H2 picks that has none yet
  python3 -m moot.heldout.h2 inputs    what each arm may see -> data/h2/inputs.json
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date

from ..backtest.labels import clone, decide, mine
from ..backtest.run import commit_dates, maintenance_events
from . import gold as G
from . import inputs as I
from .evidence import EXTRA_LICENSE_EVENTS, merged
from .tools import H2_REPOS

DATA = G.ROOT / "data" / "h2"
GOLD = G.ROOT / "eval" / "h2" / "gold.json"
T0, END = "2022-10-17", "2025-10-17"


def do_mine() -> None:
    raw = []
    for name in H2_REPOS:
        try:
            clone(name)
            raw += [d for d in (decide(r) for r in mine(name)) if d]
        except Exception as ex:  # a repository that will not clone is left out, and says so
            print("skipped", name, ex, flush=True)
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "raw.json").write_text(json.dumps(raw, indent=1) + "\n")


def do_label() -> None:
    G.T0, G.END = T0, END
    decisions = G.tag(json.loads((DATA / "raw.json").read_text()))
    (DATA / "decisions.json").write_text(json.dumps(decisions, indent=1) + "\n")
    units = [d for d in decisions if d["tools"] and G.in_force(d, T0) and d["first_commit"] <= T0]
    out, skipped = [], []
    for d in units:
        d["source"] = "h2"
        g = G.label(d)
        if g is None:
            skipped.append(d["id"])
            continue
        out.append(dict(id=d["id"], repo=d["repo"], source="h2", title=d["title"], path=d["path"], url=d["url"], born=d["born"], tools=d["tools"], **g))
    for cls in ("DEAD", "HOLDS"):
        xs = sorted((u for u in out if u["gold"] == cls), key=lambda u: hashlib.sha256(u["id"].encode()).hexdigest())
        k = round(len(xs) * G.DEV_SHARE)
        for i, u in enumerate(xs):
            u["split"] = "dev" if i < k else "test"
    out.sort(key=lambda u: u["id"])
    payload = dict(t0=T0, end=END, units=out)
    payload = dict(sha256=G.digest(payload), written=date.today().isoformat(), skipped=sorted(skipped), **payload)
    GOLD.parent.mkdir(parents=True, exist_ok=True)
    GOLD.write_text(json.dumps(payload, indent=1) + "\n")
    c = lambda **kw: sum(1 for u in out if all(u.get(k) == v for k, v in kw.items()))
    print(f"H2: {len(out)} units from {len({u['repo'] for u in out})} repositories ({len(skipped)} left out); DEAD {c(gold='DEAD')} "
          f"(dev {c(gold='DEAD', split='dev')}), HOLDS {c(gold='HOLDS')} (dev {c(gold='HOLDS', split='dev')}); sha256 {payload['sha256']}")


def do_evidence() -> None:
    have = merged()
    need = sorted({t for u in json.loads(GOLD.read_text())["units"] for t in u["tools"]} - set(have))
    out = {}
    for t in need:
        name, _, repo = G.TOOLS[t]
        if not repo:
            continue
        dates = commit_dates(repo)
        out[t] = dict(name=name, repo=repo, first_commit=dates[0], last_commit=dates[-1], commits=len(dates), maintained=maintenance_events(dates),
                      open_source=[dict(rel=rel, at=at, quote=what, source=src) for tt, at, rel, what, src in EXTRA_LICENSE_EVENTS if tt == t])
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "evidence.json").write_text(json.dumps(out, indent=1) + "\n")
    print("evidence for", sorted(out))


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    if step == "mine":
        do_mine()
    elif step == "label":
        do_label()
    elif step == "evidence":
        do_evidence()
    elif step == "inputs":
        I.main(GOLD, DATA / "inputs.json")
    else:
        sys.exit(__doc__)
