"""Dated evidence for the tools only the new repositories pick (moot/heldout/tools.py EXTRA_TOOLS), made exactly as the
backtest makes its own (moot/backtest/run.py): each tool's default-branch commit history (a gap of more than 365 days
CONTRADICTS "maintained", the next commit SUPPORTS it again) and the vendor's dated licence announcements.

  python3 -m moot.heldout.evidence      -> data/heldout/evidence_extra.json (bare, tree-less clones in data/backtest/.tools)
"""
from __future__ import annotations

import json

from ..backtest.run import commit_dates, maintenance_events
from .gold import DATA
from .tools import EXTRA_TOOLS

# (tool, date, CONTRADICTS|SUPPORTS, what happened, source), the vendor's own announcement
EXTRA_LICENSE_EVENTS = [
    ("nomad", "2023-08-10", "CONTRADICTS", "HashiCorp moves Nomad to the Business Source License", "https://www.hashicorp.com/blog/hashicorp-adopts-business-source-license"),
]


def merged() -> dict[str, dict]:
    """The backtest's evidence plus the extra tools'."""
    from .gold import ROOT
    ev = json.loads((ROOT / "data" / "backtest" / "evidence.json").read_text())
    for f in (DATA / "evidence_extra.json", ROOT / "data" / "h2" / "evidence.json"):
        if f.exists():
            ev.update({k: v for k, v in json.loads(f.read_text()).items() if k not in ev})
    return ev


def main() -> None:
    out = {}
    for t, (name, _, repo) in sorted(EXTRA_TOOLS.items()):
        if repo is None:
            continue  # no public commit history (a hosted service or a platform framework)
        dates = commit_dates(repo)
        out[t] = dict(name=name, repo=repo, first_commit=dates[0], last_commit=dates[-1], commits=len(dates), maintained=maintenance_events(dates),
                      open_source=[dict(rel=rel, at=at, quote=what, source=src) for tt, at, rel, what, src in EXTRA_LICENSE_EVENTS if tt == t])
        print(t, len(dates), "commits", len(out[t]["maintained"]), "maintenance events", flush=True)
    (DATA / "evidence_extra.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
