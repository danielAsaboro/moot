# Studies: registered before they ran, reported whatever came out

Each study below states its hypothesis, data, metric and script before its first run, with the date it was written. The result ships whatever it is. A study written after its data was seen says so. When git history exists for an entry, the commit that added it is the proof of order; an entry that is not yet committed carries only the date written here.

## S1. Graph ablation on the Larkspur gate, in both directions

- **Written:** 2026-10-18 06:58 UTC, before `eval/eval_ablation.py` existed or ran.
- **Question:** does the graph carry the gate's verdict, or would the rule text decide it anyway? Substrate-friction's control only deleted edges, so it could not tell real edges from junk. This one adds junk too.
- **Data:** `data/graph.json` (Larkspur, 30 decisions), as of `truth.json`'s date, gold = the spec's expected verdicts (an agent may act only on the 10 HOLDS).
- **Arms:**
  - delete a fraction f ∈ {0, 0.25, 0.5, 0.75, 1} of the `CONTRADICTS` edges, 20 seeds per fraction
  - delete the same fractions of the reason edges (`BECAUSE_OF` and `DERIVED_FROM`)
  - add random `CONTRADICTS` edges (random evidence → random premise, dated at a random existing evidence date on or before as-of), k = f × the number of real `CONTRADICTS` edges, f ∈ {0, 0.25, 0.5, 1, 2}
- **Metrics:** false allows (of the 20 that should be stopped), stale decisions allowed (of the 16 MOOT/DISPUTED), false blocks and holds decisions denied (of the 10 HOLDS). Each under the current gate and under the legacy rule where a premise with no evidence counted as holding.
- **Predictions:**
  1. Legacy rule: false allows climb with CONTRADICTS deletion toward the stale count (16) at f = 1, because a premise whose contradiction is deleted reads as holding.
  2. Current rule: false allows stay much lower under the same deletion, because a premise left with no evidence becomes `unevidenced` and the gate says REVALIDATE. Only premises that also carry support can be let through.
  3. Reason-edge deletion: false allows rise at middle fractions (a dead premise disconnected from a decision whose other premises have support), then fall to 0 at f = 1 (every decision UNDOCUMENTED, so REVALIDATE).
  4. Added CONTRADICTS edges: holds decisions denied climbs from 0 with k; false allows stay at 0.
- **Script:** `python3 eval/eval_ablation.py` → `eval/results_ablation.md` and `.json`.

## S2. Gate eval after the empty-evidence fix

- **Written:** 2026-10-18 06:58 UTC, after the hydradb-oss-hack teardown counted the effect by hand (ALLOW 10 → 4), before `eval/eval_gate.py` was re-run.
- **Change:** `premise_state([])` returns `unevidenced` instead of `holds`; the gate says REVALIDATE on it. The verdict (HOLDS) does not change.
- **Prediction:** ALLOW 10 → 4 (D12, D14, D15, D24); false allows stay 0; false blocks 0 → 6, all REVALIDATE with `premise_unevidenced` (D06, D10, D16, D22, D26, D27). The verdict eval (30/30) does not move.
- **Script:** `python3 eval/eval_gate.py`.

## Registered after the fact

- **Backtest** (`eval/results_backtest.md`). The answer key (maintainers' own status changes) was fixed by code before the gate ran, but this file did not exist then, so the order rests on the results file's own account. Its gate was replayed before the empty-evidence fix; its score counts DENY only, which the fix does not touch (the fix turns some ALLOWs into REVALIDATE).
- **ERAG blind v1** (`eval/results_erag.md`). Frozen before its first run on any benchmark pool; the freeze record and hashes are in `evidence/run_manifest.json`. v2 is labelled post-hoc everywhere it appears.

## Withdrawn results

Kept here so the surviving numbers can be read against what was claimed before.

| withdrawn | was | why | replaced by |
|---|---|---|---|
| Gate eval, Moot row: 10 ALLOW, 0 false blocks | `eval/results_gate.md` before 2026-10-18 | Six of the ten ALLOWs (D06, D10, D16, D22, D26, D27) rested on a premise with no evidence at all; the gate printed "all premises hold" when nothing had checked them (found by the hydradb-oss-hack teardown). | S2 above: 4 ALLOW, 6 false blocks, all REVALIDATE |
| Retrieval recall@5 = 1.00 read as a retrieval result | README and `eval/results.md` | The targets are the CONTRADICTS edges in `truth.json` and the graph's CONTRADICTS edges come from the same spec, so the graph reads back its own edges. The number stands as a consistency check, not as evidence that the graph finds documents. | same number, labelled as a consistency check |
| Latency columns "full ledger" and "SPpaths trace" | `eval/results_scale.md` before 2026-10-18 | One timing each, no warm/cold split, so 3, 3, 9, 3 ms was noise. | n, p50, p95 and a cold first call per row |
| ERAG v2 as a result in its own right | — | Not withdrawn, but written after v1 was scored; it is labelled post-hoc and never the headline. | v1 stays the headline |
