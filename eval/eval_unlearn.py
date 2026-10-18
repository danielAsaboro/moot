"""Study U1: are remembered gate answers revoked when the evidence under them changes? (docs/studies.md U1)

Every decision in Larkspur, the backtest and the four ingested repositories is asked about at every month start from its date
to the snapshot, seeing only what was known by then. Three memory policies answer:
  moot       serve the remembered answer while the fingerprint of the rows it rests on is unchanged (every premise to depth 6
             with its known dated events, what retires the decision, its owner); else re-audit and remember the new answer
  ttl90      serve the remembered answer for 90 days, then re-audit
  ttl365     the same for a year
A fresh audit every month is the reference. No model, no writes.

  python3 eval/eval_unlearn.py       -> eval/results_unlearn.{md,json}
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from moot import tools  # noqa: E402
from moot.connectors import github as gh  # noqa: E402
from moot.graph import BACKTEST_GRAPH, DATA, connect, seed  # noqa: E402
from moot.verdict import gate  # noqa: E402

OUT = Path(os.getenv("MOOT_EVAL_OUT") or ROOT / "eval")
END = {"larkspur": "2026-10-16", "backtest": "2026-10-17"}
POLICIES = ("moot", "ttl90", "ttl365")


def months(start: str, end: str) -> list[str]:
    y, m = int(start[:4]), int(start[5:7])
    out = []
    while True:
        m += 1
        if m == 13:
            y, m = y + 1, 1
        d = f"{y:04d}-{m:02d}-01"
        if d > end:
            return out
        out.append(d)


def fingerprint(a: dict) -> str:
    rows = [sorted((p["id"], sorted((e["id"], e["rel"], e["at"], e.get("stated")) for e in p["evidence"])) for p in a.get("premises", [])),
            (a.get("superseded_by") or {}).get("id"), (a.get("owner") or {}).get("id"), (a.get("owner") or {}).get("active"), a.get("verdict")]
    return hashlib.sha256(json.dumps(rows, default=str).encode()).hexdigest()[:16]


def replay(g, end: str) -> dict:
    cov = tools.coverage(g)
    ids = [r[0] for r in g.ro_query("MATCH (d:Decision) RETURN d.id, d.decided_on ORDER BY d.id").result_set]
    born = dict(g.ro_query("MATCH (d:Decision) RETURN d.id, d.decided_on").result_set)
    stats = {p: dict(asked=0, from_memory=0, stale=0, stale_clearance=0) for p in POLICIES}
    for did in ids:
        mem = {p: None for p in POLICIES}
        for m in months(born[did] or "2015-01-01", end):
            a = tools.audit_decision(g, did, m, tools.GATE_DEPTH)
            truth = gate(a, cov)["gate"]
            fp = fingerprint(a)
            for p in POLICIES:
                s, x = stats[p], mem[p]
                s["asked"] += 1
                if p == "moot":
                    hit = x is not None and x["fp"] == fp
                else:
                    ttl = 90 if p == "ttl90" else 365
                    hit = x is not None and (date.fromisoformat(m) - date.fromisoformat(x["at"])).days < ttl
                if hit:
                    s["from_memory"] += 1
                    if x["gate"] != truth:
                        s["stale"] += 1
                        s["stale_clearance"] += x["gate"] == "ALLOW"
                else:
                    mem[p] = dict(gate=truth, fp=fp, at=m)
    return dict(decisions=len(ids), **stats)


def main() -> None:
    db = connect()
    graphs = {"larkspur": DATA / "graph.json", BACKTEST_GRAPH: DATA / "backtest" / "graph.json"}
    graphs.update({gh.graph_name(r): gh.load(r) for r in ["npryce/adr-tools", "thomvaill/log4brains", "alphagov/govuk-infrastructure", "alphagov/govuk-aws"]})
    res = {}
    for name, f in graphs.items():
        g = db.select_graph(f"moot_eval_unlearn_{name}")
        seed(g, f, fresh=True)
        try:
            end = END.get(name) or json.loads((f.parent / "summary.json").read_text())["read_on"]
            res[name] = replay(g, end)
        finally:
            g.delete()
        print(name, res[name], flush=True)
    tot = {p: {k: sum(r[p][k] for r in res.values()) for k in ("asked", "from_memory", "stale", "stale_clearance")} for p in POLICIES}
    (OUT / "results_unlearn.json").write_text(json.dumps(dict(graphs=res, total=tot), indent=1) + "\n")
    L = ["# Un-learning: remembered gate answers, revoked when their evidence changes (study U1)", "",
         "Every decision in Larkspur, the backtest and the four ingested repositories, asked about at every month start from its date to the "
         "snapshot, seeing only what was known then. *Stale* means the remembered answer differs from a fresh audit that month; a *stale "
         "clearance* is a remembered ALLOW served when a fresh audit would block. No model, no writes.", "",
         "| policy | questions | answered from memory | stale answers served | stale clearances served |", "|---|---|---|---|---|"]
    names = dict(moot="**Moot: serve while the rows' fingerprint is unchanged**", ttl90="cache for 90 days", ttl365="cache for a year")
    for p in POLICIES:
        t = tot[p]
        L.append(f"| {names[p]} | {t['asked']:,} | {t['from_memory']:,} ({t['from_memory'] / t['asked']:.0%}) | {t['stale']:,} | {t['stale_clearance']:,} |")
    L += ["", "| graph | decisions | Moot from memory | Moot stale | 90-day stale | 365-day stale |", "|---|---|---|---|---|---|"]
    for name, r in res.items():
        L.append(f"| {name} | {r['decisions']} | {r['moot']['from_memory'] / r['moot']['asked']:.0%} | {r['moot']['stale']} | {r['ttl90']['stale']} | {r['ttl365']['stale']} |")
    L += ["", "Moot's zero is by construction: the fingerprint covers every row the gate reads, so a change in any of them forces a re-audit. "
          "What the table measures is the price of that guarantee (how often memory still answers) and what a time-based cache gets wrong instead."]
    (OUT / "results_unlearn.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
