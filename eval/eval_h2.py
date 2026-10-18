"""Study H2 (docs/studies.md): H1's machinery on a fresh set, the product gate policy, balanced accuracy primary. Run once.

  python3 eval/eval_h2.py --llm      fill the model caches (eval/h2/*.jsonl) for every unit, then score
  python3 eval/eval_h2.py            score from the caches -> eval/results_h2.{md,json}
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ["MOOT_HELDOUT_STUDY"] = "h2"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_heldout as E  # noqa: E402

ARMS = ("moot_warn", "majority", "trust_adr", "age", "rag_bm25", "agent_tools")
LABEL = dict(moot_warn="**Moot gate, product policy (warn)**", majority="majority class (dev)", trust_adr="trust the ADR's status",
             age="age ≥ 3 years", rag_bm25=f"BM25 RAG + {E.RAG_MODEL}", agent_tools=f"LLM agent with GitHub/OSV tools ({E.AGENT_MODEL})")


def main() -> None:
    E.refuse_if_gold_changed()
    fill = "--llm" in sys.argv
    every = [g["id"] for g in E.GOLD["units"]]
    m = E.arm_moot()
    preds = dict(moot_warn={i: dict(pred="DEAD" if v["gate_warn"] == "DENY" else "HOLDS", why=v["why"]) for i, v in m.items()},
                 majority=E.arm_majority(), trust_adr=E.arm_trust(), age=E.arm_age(),
                 rag_bm25=E.arm_rag(fill, every), agent_tools=E.arm_agent(fill, every))
    res = {}
    for split in ("test", "dev", "all"):
        us = [g for g in E.GOLD["units"] if split == "all" or g["split"] == split]
        res[split] = {a: E.score(preds[a], us) for a in ARMS}
        res[split]["paired_vs_moot"] = {a: E.paired(preds["moot_warn"], preds[a], us) for a in ARMS if a != "moot_warn"}
    (E.OUT / "results_h2.json").write_text(json.dumps(dict(t0=E.T0, end=E.GOLD["end"], gold_sha256=E.GOLD["sha256"], results=res,
                                                        rows=[dict(id=g["id"], split=g["split"], gold=g["gold"], **{a: preds[a].get(g["id"], {}).get("pred") for a in ARMS})
                                                              for g in E.GOLD["units"]]), indent=1) + "\n")
    t = res["test"]
    L = ["# H2: a fresh held-out set, the product gate policy (study H2)", "",
         f"{len(E.GOLD['units'])} decisions from repositories outside the backtest and H1, in force on {E.T0}, graded on {E.GOLD['end']} by the H1 rule; "
         f"gold hashed before any arm ran (`{E.GOLD['sha256'][:16]}…`). **Underpowered:** {sum(g['gold'] == 'DEAD' for g in E.GOLD['units'])} decision died, "
         "so balanced accuracy, the registered primary metric, swings on one call. Run once, as registered.", "",
         f"## Test split ({t['moot_warn']['n']} decisions, {t['moot_warn']['dead']} DEAD)", "",
         "| arm | balanced accuracy (primary) | right | DEAD caught | held decisions called DEAD (blocked) | vs Moot (only Moot right / only it right, p) |",
         "|---|---|---|---|---|---|"]
    for a in ARMS:
        s = t[a]
        pv = t["paired_vs_moot"].get(a)
        L.append(f"| {LABEL[a]} | {s['balanced_accuracy']:.2f} | {s['right']}/{s['n']} | {s['caught']}/{s['dead']} | {s['flagged'] - s['caught']}/{s['holds']} | "
                 + (f"{pv['only_moot']} / {pv['only_other']}, p = {pv['p']:.3f}" if pv else "–") + " |")
    a_ = res["all"]
    L += ["", f"All {a_['moot_warn']['n']} decisions (dev and test; nothing was tuned on dev): " + ", ".join(
        f"{LABEL[a].strip('*')} {a_[a]['right']}/{a_[a]['n']} right, {a_[a]['caught']}/{a_[a]['dead']} caught, {a_[a]['flagged'] - a_[a]['caught']} false alarms" for a in ARMS) + "."]
    (E.OUT / "results_h2.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[5:14]))


if __name__ == "__main__":
    main()
