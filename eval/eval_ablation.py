"""Graph ablation on the Larkspur gate, in both directions (pre-registered as S1 in docs/studies.md).

Does the graph carry the gate's verdict, or would the rule text decide it anyway?

  delete CONTRADICTS   remove a fraction of the dated contradictions
  delete reasons       remove a fraction of BECAUSE_OF / DERIVED_FROM edges (decision → premise → premise)
  add CONTRADICTS      add random contradictions: random evidence → random premise, at a random real evidence date

Each arm is scored under the current gate and under the legacy rule, where a premise with no evidence counted as holding.
Gold: an agent may act only on the decisions whose expected verdict is HOLDS. No model. Writes eval/results_ablation.md
and eval/results_ablation.json.
"""
from __future__ import annotations

import json
import os
import random
import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from moot import tools  # noqa: E402
from moot.graph import DATA, connect, seed  # noqa: E402
from moot.stats import wilson_upper  # noqa: E402
from moot.verdict import BLOCKING, gate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.getenv("MOOT_EVAL_OUT") or ROOT / "eval")  # `moot verify --rerun` writes elsewhere and compares
SEEDS = 20
DELETE = [0, 0.25, 0.5, 0.75, 1]
ADD = [0, 0.25, 0.5, 1, 2]
REASON_EDGES = ("BECAUSE_OF", "DERIVED_FROM")


def legacy(result: dict) -> str:
    """The gate as it was before 2026-10-18: a premise with no evidence counted as holding."""
    rs = [r for r in result["reasons"] if r["code"] != "premise_unevidenced"]
    return "DENY" if any(r["code"] in BLOCKING for r in rs) else "REVALIDATE" if rs else "ALLOW"


def run(g, payload: dict, gold: dict, as_of: str) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
    seed(g, Path(f.name), fresh=True)
    Path(f.name).unlink()
    cov = tools.coverage(g)
    out = {}
    for k in gold:
        r = gate(tools.audit_decision(g, k, as_of, tools.GATE_DEPTH), cov)
        out[k] = dict(current=r["gate"], legacy=legacy(r))
    return score(out, gold)


def score(gates: dict, gold: dict) -> dict:
    res = {}
    for rule in ("current", "legacy"):
        allowed = {k for k, v in gates.items() if v[rule] == "ALLOW"}
        res[rule] = dict(
            false_allows=sum(1 for k in allowed if gold[k] != "HOLDS"),
            stale_allowed=sum(1 for k in allowed if gold[k] in ("MOOT", "DISPUTED")),
            false_blocks=sum(1 for k in gold if gold[k] == "HOLDS" and k not in allowed),
            holds_denied=sum(1 for k, v in gates.items() if gold[k] == "HOLDS" and v[rule] == "DENY"))
    return res


def mutate_delete(payload: dict, rels: tuple[str, ...], frac: float, rng: random.Random) -> dict:
    idx = [i for i, e in enumerate(payload["edges"]) if e["rel"] in rels]
    drop = set(rng.sample(idx, round(frac * len(idx))))
    return dict(nodes=payload["nodes"], edges=[e for i, e in enumerate(payload["edges"]) if i not in drop])


def mutate_add(payload: dict, k: int, as_of: str, rng: random.Random) -> dict:
    ev = [n["id"] for n in payload["nodes"] if n["label"] == "Evidence"]
    pr = [n["id"] for n in payload["nodes"] if n["label"] == "Premise"]
    dates = sorted({e["props"]["at"] for e in payload["edges"] if e["rel"] in ("SUPPORTS", "CONTRADICTS") and e["props"]["at"] <= as_of})
    have = {(e["src"], e["dst"]) for e in payload["edges"] if e["rel"] in ("SUPPORTS", "CONTRADICTS")}
    junk = []
    while len(junk) < k:
        s, d = rng.choice(ev), rng.choice(pr)
        if (s, d) in have:
            continue
        have.add((s, d))
        junk.append(dict(src=s, dst=d, rel="CONTRADICTS", props=dict(at=rng.choice(dates), quote="(ablation: random edge)")))
    return dict(nodes=payload["nodes"], edges=payload["edges"] + junk)


def agg(runs: list[dict]) -> dict:
    out = {}
    for rule in ("current", "legacy"):
        out[rule] = {m: dict(mean=round(statistics.mean(r[rule][m] for r in runs), 2), min=min(r[rule][m] for r in runs),
                             max=max(r[rule][m] for r in runs)) for m in runs[0][rule]}
    out["n"] = len(runs)
    return out


def main() -> None:
    truth = json.loads((DATA / "truth.json").read_text())
    payload = json.loads((DATA / "graph.json").read_text())
    as_of = truth["as_of"]
    gold = {d["id"]: d["expected"] for d in truth["decisions"]}
    g = connect().select_graph("moot_eval_ablation")
    n_contra = sum(1 for e in payload["edges"] if e["rel"] == "CONTRADICTS")
    n_reason = sum(1 for e in payload["edges"] if e["rel"] in REASON_EDGES)
    arms = {}
    for name, rels in (("delete_contradicts", ("CONTRADICTS",)), ("delete_reasons", REASON_EDGES)):
        arms[name] = []
        for f in DELETE:
            seeds = 1 if f in (0, 1) else SEEDS
            runs = [run(g, mutate_delete(payload, rels, f, random.Random(1000 * s + int(f * 100))), gold, as_of) for s in range(seeds)]
            arms[name].append(dict(level=f, **agg(runs)))
    arms["add_contradicts"] = []
    for f in ADD:
        k = round(f * n_contra)
        seeds = 1 if k == 0 else SEEDS
        runs = [run(g, mutate_add(payload, k, as_of, random.Random(1000 * s + k)), gold, as_of) for s in range(seeds)]
        arms["add_contradicts"].append(dict(level=f, added=k, **agg(runs)))
    g.delete()
    n_block = sum(1 for v in gold.values() if v != "HOLDS")
    n_stale = sum(1 for v in gold.values() if v in ("MOOT", "DISPUTED"))
    n_hold = len(gold) - n_block
    result = dict(as_of=as_of, seeds=SEEDS, n_block=n_block, n_stale=n_stale, n_hold=n_hold, contradicts=n_contra,
                  reason_edges=n_reason, arms=arms)
    (OUT / "results_ablation.json").write_text(json.dumps(result, indent=1) + "\n")
    (OUT / "results_ablation.md").write_text(render(result))
    print(render(result))


def cell(x: dict) -> str:
    return f"{x['mean']:g}" if x["min"] == x["max"] else f"{x['mean']:g} ({x['min']}–{x['max']})"


def render(r: dict) -> str:
    nb, ns, nh = r["n_block"], r["n_stale"], r["n_hold"]
    out = ["# Graph ablation: does the graph carry the gate's verdict?", "",
           f"Pre-registered as S1 in [docs/studies.md](../docs/studies.md) before the first run. Larkspur as of {r['as_of']}: "
           f"{nh} decisions HOLD and may be acted on; {nb} should be stopped, {ns} of them MOOT or DISPUTED. "
           f"Each cell is the mean over {r['seeds']} random seeds (range in brackets) except at 0% and 100%, which are deterministic. "
           "*Legacy* is the gate before 2026-10-18, when a premise with no evidence counted as holding.", ""]
    head = (f"| deleted | false allows, current (of {nb}) | stale allowed, current (of {ns}) | false allows, legacy | stale allowed, legacy | "
            f"false blocks, current (of {nh}) |")
    for name, title, n in (("delete_contradicts", f"## Delete dated contradictions ({r['contradicts']} edges)", r["contradicts"]),
                           ("delete_reasons", f"## Delete reason edges: BECAUSE_OF and DERIVED_FROM ({r['reason_edges']} edges)", r["reason_edges"])):
        out += [title, "", head, "|---|---|---|---|---|---|"]
        for row in r["arms"][name]:
            c, l = row["current"], row["legacy"]
            out.append(f"| {int(row['level'] * 100)}% | {cell(c['false_allows'])} | {cell(c['stale_allowed'])} | {cell(l['false_allows'])} | "
                       f"{cell(l['stale_allowed'])} | {cell(c['false_blocks'])} |")
        out.append("")
    out += [f"## Add random contradictions (k = multiple of the {r['contradicts']} real ones)", "",
            f"| added | holds decisions denied, current (of {nh}) | false blocks, current (of {nh}) | holds denied, legacy | false blocks, legacy | false allows, current |",
            "|---|---|---|---|---|---|"]
    for row in r["arms"]["add_contradicts"]:
        c, l = row["current"], row["legacy"]
        out.append(f"| {row['added']} ({row['level']:g}×) | {cell(c['holds_denied'])} | {cell(c['false_blocks'])} | {cell(l['holds_denied'])} | "
                   f"{cell(l['false_blocks'])} | {cell(c['false_allows'])} |")
    a = r["arms"]
    base = a["delete_contradicts"][0]["current"]
    dc_full = a["delete_contradicts"][-1]
    reason_max = max(row["current"]["false_allows"]["max"] for row in a["delete_reasons"])
    reason_max_legacy = max(row["legacy"]["false_allows"]["max"] for row in a["delete_reasons"])
    add_last = a["add_contradicts"][-1]
    add_fa = max(row["current"]["false_allows"]["max"] for row in a["add_contradicts"])
    out += ["", "## Against the predictions in S1", "",
            f"At 0% the current gate lets through {base['false_allows']['mean']:g} of {nb}; the one-sided 95% upper bound on its "
            f"false-allow rate is still {wilson_upper(int(base['false_allows']['mean']), nb):.2f}.", "",
            f"1. **Legacy rule, delete contradictions: held.** False allows climb to {dc_full['legacy']['false_allows']['mean']:g} of {nb} with every "
            f"contradiction gone. Not all {ns}: the other stale decisions are still stopped because their owner left.",
            f"2. **Current rule, same deletion: held.** {dc_full['current']['false_allows']['mean']:g} of {nb} get through. A premise whose only "
            "evidence was deleted becomes unevidenced and the gate asks to revalidate; only premises that also carry support (the disputed ones) "
            "read as holding.",
            f"3. **Reason-edge deletion: failed.** We predicted false allows would rise at middle fractions; the maximum over all seeds is "
            f"{reason_max} (legacy {reason_max_legacy}). Every stale Larkspur decision states exactly one premise, so cutting the chain to the dead "
            "premise either leaves the decision with no premise (UNDOCUMENTED, so REVALIDATE) or leaves one whose owner has left. What climbs "
            "instead is false blocks. This is a property of the corpus, not evidence that the rule is robust to missing reasons.",
            f"4. **Added contradictions: held.** Holds decisions denied climbs to {add_last['current']['holds_denied']['mean']:g} of {nh} at "
            f"{add_last['added']} junk edges, and false allows stay at {add_fa}. The gate follows the edges it is given, junk included: it cannot "
            "tell a plausible wrong contradiction from a real one, which is why every DENY names the evidence id for a human to check.", "",
            "## Threats to validity, worst first", "",
            "1. The graph and the gold come from the same spec. The ablation shows which edges the gate's answers depend on; it does not show that "
            "those edges could be extracted from raw text.",
            "2. Thirty decisions. A one-decision change is 3–10 points on these scales; the seed ranges show how much of each mean is the draw.",
            "3. Random junk is easier to tell from real evidence than a plausible wrong edge an extractor would write. Real extraction errors would "
            "be more correlated with the decision's own vocabulary than these.",
            "4. Deleting reason edges also removes the premises a decision is checked against, so part of what this arm measures is the gate's "
            "UNDOCUMENTED rule, not the evidence.", ""]
    return "\n".join(out)


if __name__ == "__main__":
    main()
