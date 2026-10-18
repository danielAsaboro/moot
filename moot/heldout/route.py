"""Who a blocked agent could have asked on T0, for each H1 decision: the people who wrote the ADR (its git authors up to T0)
who were still committing to the repository in the year before T0. Read from the clones; nothing here is a label.

  python3 -m moot.heldout.route      -> data/heldout/route.json
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from ..backtest.labels import REPOS_DIR, git
from .gold import DATA, GOLD, rev_at


def main() -> None:
    gold = json.loads(GOLD.read_text())
    t0 = gold["t0"]
    since = (date.fromisoformat(t0) - timedelta(days=365)).isoformat()
    inputs = {u["id"]: u for u in json.loads((DATA / "inputs.json").read_text())["units"]}
    active_cache: dict[str, set] = {}
    out = {}
    for u in gold["units"]:
        repo = REPOS_DIR / u["repo"].replace("/", "__")
        r0 = rev_at(repo, t0)
        path = inputs[u["id"]]["path_t0"] or u["path"]
        authors = list(dict.fromkeys(git(repo, "log", "--follow", "--format=%an <%ae>", r0, "--", path).splitlines()[::-1])) if r0 else []
        if u["repo"] not in active_cache:
            active_cache[u["repo"]] = set(git(repo, "log", f"--since={since}", "--format=%an <%ae>", r0).splitlines()) if r0 else set()
        still = [a for a in authors if a in active_cache[u["repo"]]]
        out[u["id"]] = dict(authors=len(authors), still_active=len(still), ask=still[0].split(" <")[0] if still else None)
    (DATA / "route.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(f"{sum(1 for v in out.values() if v['ask'])} of {len(out)} decisions had an author still committing in the year before {t0}")


if __name__ == "__main__":
    main()
