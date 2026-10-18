"""Backtest: rewind real repositories and ask whether Moot's gate stopped decisions before their maintainers did.

  python3 -m moot.backtest.run         evidence -> data/backtest/graph.json -> FalkorDB graph `backtest` -> data/backtest/gates.json

Leakage control is Moot's own time travel: every Evidence edge carries the date the fact became knowable
(`at`), and the gate is asked `as_of` each cutoff, so it can only see what existed then. The answer key
(labels.py) is never written into this graph: no RETIRES edges, so a decision is never denied for having died.

Evidence, per tool the decision's title picks:
  maintained    the tool's own default branch, read from git: a gap of more than 365 days without a commit
                CONTRADICTS "<tool> is actively maintained" on the day the gap reaches 365 days; the next commit SUPPORTS it again
  open source   a dated license change announced by the vendor (tools.LICENSE_EVENTS)
The live checker's third premise, "no known vulnerability", is left out: OSV records when an advisory was
published, but not which release a team could have been on at a past date, so it cannot be replayed honestly.
"""
from __future__ import annotations

import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

from ..graph import graph, seed
from ..tools import check_action
from .labels import OUT
from .tools import LICENSE_EVENTS, TOOLS

GRAPH = "backtest"
END = "2026-10-17"  # the snapshot date: the day the histories were read
TOOLS_DIR = OUT / ".tools"
STALE = 365


def commit_dates(repo: str) -> list[str]:
    d = TOOLS_DIR / (repo.replace("/", "__") + ".git")
    if not d.exists():
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--bare", "--filter=tree:0", "--single-branch", f"https://github.com/{repo}", str(d)],
                       check=True, timeout=1800)
    out = subprocess.run(["git", "-C", str(d), "log", "--format=%cs", "HEAD"], capture_output=True, text=True, check=True).stdout
    return sorted({x for x in out.split() if x <= END})


def maintenance_events(dates: list[str]) -> list[dict]:
    """Dated SUPPORTS/CONTRADICTS for "actively maintained", knowable on the day each is dated."""
    ev, prev = [], None
    for d in dates + [None]:
        if prev:
            limit = (date.fromisoformat(prev) + timedelta(days=STALE)).isoformat()
            if (d or END) > limit and limit <= END:
                ev.append(dict(rel="CONTRADICTS", at=limit, quote=f"no commit to the default branch since {prev}"))
                if d:
                    ev.append(dict(rel="SUPPORTS", at=d, quote=f"commits resume on {d} after a gap since {prev}"))
        prev = d
    return ev


def evidence(tool_ids: set[str]) -> dict[str, dict]:
    out = {}
    for t in sorted(tool_ids):
        name, _, repo = TOOLS[t]
        dates = commit_dates(repo)
        out[t] = dict(name=name, repo=repo, first_commit=dates[0], last_commit=dates[-1], commits=len(dates),
                      maintained=maintenance_events(dates),
                      open_source=[dict(rel=rel, at=at, quote=what, source=src) for tt, at, rel, what, src in LICENSE_EVENTS if tt == t])
    return out


PREMISE = {"maintained": "{name} is actively maintained", "open_source": "{name} is open source"}


def build(decisions: list[dict], ev: dict[str, dict]) -> dict:
    nodes, edges = [], []
    for t, e in ev.items():
        for k in PREMISE:
            pid = f"p_{t}_{k}"
            nodes.append(dict(label="Premise", id=pid, props=dict(text=PREMISE[k].format(name=e["name"]), kind="unwritten", tool=t, check=k)))
            for i, x in enumerate(e[k]):
                eid = f"{k}:{t}:{x['at']}"
                title = (f"git history of {e['repo']}: {x['quote']}" if k == "maintained" else f"{x['quote']} ({x['source']})")
                nodes.append(dict(label="Evidence", id=eid, props=dict(kind="check", title=title, date=x["at"], excerpt=x["quote"],
                                                                       path=x.get("source") or f"https://github.com/{e['repo']}")))
                edges.append(dict(src=eid, rel=x["rel"], dst=pid, props=dict(at=x["at"], quote=x["quote"])))
    for d in decisions:
        nodes.append(dict(label="Decision", id=d["id"], props=dict(title=d["title"], summary=d["title"], decided_on=d["born"], source=d["url"],
                                                                   repo=d["repo"], status="accepted")))
        for t in d["tools"]:
            for k in PREMISE:
                edges.append(dict(src=d["id"], rel="BECAUSE_OF", dst=f"p_{t}_{k}", props=dict(quote=PREMISE[k].format(name=ev[t]["name"]))))
    return dict(nodes=nodes, edges=edges)


def months(start: str, end: str) -> list[str]:
    y, m = int(start[:4]), int(start[5:7])
    out = []
    while True:
        m += 1
        if m == 13:
            y, m = y + 1, 1
        d = f"{y:04d}-{m:02d}-01"
        if d >= end:
            return out
        out.append(d)


def in_force_until(d: dict) -> str:
    return min(x for x in (d["death"]["date"] if d["death"] else None, d["deleted"], END) if x)


def main() -> None:
    decisions = [d for d in json.loads((OUT / "decisions.json").read_text()) if d["tools"]]
    ev = evidence({t for d in decisions for t in d["tools"]})
    (OUT / "evidence.json").write_text(json.dumps(ev, indent=1))
    payload = build(decisions, ev)
    (OUT / "graph.json").write_text(json.dumps(payload, indent=1))
    g = graph(GRAPH)
    seed(g, OUT / "graph.json", fresh=True)
    gates = {}
    for d in decisions:
        series = []
        for c in [d["born"]] + months(d["born"], in_force_until(d)):  # only while the decision is in force: the label never shows
            a = check_action(g, d["id"], c, policy="strict")
            series.append(dict(as_of=c, gate=a["gate"], reasons=[r["text"] for r in a["reasons"]]))
        gates[d["id"]] = series
    (OUT / "gates.json").write_text(json.dumps(gates, indent=1))
    print(f"{len(decisions)} tool decisions, {sum(len(s) for s in gates.values())} gate calls against FalkorDB graph '{GRAPH}'")


if __name__ == "__main__":
    main()
