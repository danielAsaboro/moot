"""Study H3 (docs/studies.md): decisions from repositories no earlier study used, for ranking by risk. H2's code, more repositories.

  python3 -m moot.heldout.h3 candidates  GitHub code search for ADR folders -> data/h3/candidates.json (minus every repository
                                          the backtest, H1 or H2 used)
  python3 -m moot.heldout.h3 mine        clone and parse them -> data/h3/raw.json (resumable: one repository at a time)
  python3 -m moot.heldout.h3 label       tag tools, label with the H1 rule at T0 = 2022-10-17 / END = 2025-10-17, split, hash
                                          -> eval/h3/gold.json (pin its sha256 in eval/h3/GOLD.sha256 and commit before any score)
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import date

from ..backtest.labels import decide, mine
from ..backtest.labels import REPOS as BACKTEST_REPOS
from . import gold as G
from .tools import H2_REPOS, NEW_REPOS

DATA = G.ROOT / "data" / "h3"
GOLD = G.ROOT / "eval" / "h3" / "gold.json"
T0, END = "2022-10-17", "2025-10-17"
QUERIES = ["filename:0001-record-architecture-decisions.md", "filename:0002-use-markdown-architectural-decision-records.md"]


def used() -> set[str]:
    names = {r if isinstance(r, str) else r[0] for r in BACKTEST_REPOS}
    return {n.lower() for n in names | set(NEW_REPOS) | set(H2_REPOS)}


def do_candidates() -> None:
    found: dict[str, int] = {}
    for q in QUERIES:
        for page in range(1, 11):  # the code search API stops at 1,000 results
            r = subprocess.run(["gh", "api", "-X", "GET", "search/code", "-f", f"q={q}", "-f", "per_page=100", "-f", f"page={page}"],
                               capture_output=True, text=True)
            if r.returncode:
                print("search stopped:", r.stderr.strip()[:200], flush=True)
                break
            items = json.loads(r.stdout).get("items", [])
            for it in items:
                repo = it["repository"]
                if not repo.get("fork") and not repo.get("private"):
                    found[repo["full_name"]] = found.get(repo["full_name"], 0) + 1
            if len(items) < 100:
                break
            time.sleep(7)  # code search allows 10 requests a minute
    skip = used()
    out = sorted(n for n in found if n.lower() not in skip)
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "candidates.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"H3: {len(found)} repositories found, {len(out)} not used by any earlier study", flush=True)


def do_mine() -> None:
    cands = json.loads((DATA / "candidates.json").read_text())
    done_f = DATA / "mined.jsonl"
    done = {json.loads(l)["repo"] for l in done_f.read_text().splitlines()} if done_f.exists() else set()
    for name in cands:
        if name in done:
            continue
        try:
            recs = [d for d in (decide(r) for r in mine(name)) if d]
            row = dict(repo=name, decisions=recs)
        except Exception as ex:  # a repository that will not clone or parse is left out, and says so
            row = dict(repo=name, decisions=[], skipped=str(ex)[:200])
        with done_f.open("a") as f:
            f.write(json.dumps(row) + "\n")
        print(name, len(row["decisions"]), row.get("skipped", ""), flush=True)
    raw = [d for l in done_f.read_text().splitlines() for d in json.loads(l)["decisions"]]
    (DATA / "raw.json").write_text(json.dumps(raw, indent=1) + "\n")


def do_label() -> None:
    G.T0, G.END = T0, END
    decisions = G.tag(json.loads((DATA / "raw.json").read_text()))
    units = [d for d in decisions if d["tools"] and G.in_force(d, T0) and d["first_commit"] <= T0]
    out, skipped = [], []
    for d in units:
        d["source"] = "h3"
        g = G.label(d)
        if g is None:
            skipped.append(d["id"])
            continue
        out.append(dict(id=d["id"], repo=d["repo"], source="h3", title=d["title"], path=d["path"], url=d["url"], born=d["born"], tools=d["tools"], **g))
    for cls in ("DEAD", "HOLDS"):  # 30% dev within each class, by sha256 of the unit id
        xs = sorted((u for u in out if u["gold"] == cls), key=lambda u: hashlib.sha256(u["id"].encode()).hexdigest())
        k = round(len(xs) * 0.3)
        for i, u in enumerate(xs):
            u["split"] = "dev" if i < k else "test"
    out.sort(key=lambda u: u["id"])
    payload = dict(t0=T0, end=END, units=out)
    payload = dict(sha256=G.digest(payload), written=date.today().isoformat(), skipped=sorted(skipped), **payload)
    GOLD.parent.mkdir(parents=True, exist_ok=True)
    GOLD.write_text(json.dumps(payload, indent=1) + "\n")
    c = lambda **kw: sum(1 for u in out if all(u.get(k) == v for k, v in kw.items()))
    print(f"H3: {len(out)} units from {len({u['repo'] for u in out})} repositories ({len(skipped)} left out); DEAD {c(gold='DEAD')} "
          f"(test {c(gold='DEAD', split='test')}), HOLDS {c(gold='HOLDS')}; sha256 {payload['sha256']}")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    {"candidates": do_candidates, "mine": do_mine, "label": do_label}.get(step, lambda: sys.exit(__doc__))()
