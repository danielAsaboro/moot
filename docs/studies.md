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

## S3. Head-to-head: graph verdicts against a retrieval company brain, with ablations

- **Written:** 2026-10-19 16:40 UTC, after the question set was frozen and before any arm ran (deterministic or model).
- **Question:** asked *does decision X still hold as of T, which documents show it, since when?*, how does a retrieval company brain compare with Moot's graph verdict, and which part of Moot carries the answer: depth, dates, or FalkorDB itself?
- **Data:** `eval/baseline/questions.json`, 90 questions (Larkspur's 30 decisions on 2026-10-16, 2025-06-01 and 2026-01-01), frozen by `eval/baseline_questions.py` from `truth.json` alone with a verdict rule written independently of `moot/verdict.py`; it reproduces the spec's expected verdicts on all 30 (asserted). sha256 of the file: `5431b7b273fb44368e119090fc9d170cb650a7d8fd7bda8ae2bbd261c9ee9d45`.
- **Arms:** Moot (depth 4, as of T; *since* from `tools.verdict_history`); Moot rows handed to the model; RAG = the ADR + BM25 top-5 + the model; RAG over the ADR's stated reasons + the model (FalkorDB removed, model kept); ablations: depth 1, dates ignored, FalkorDB removed with the rules kept; trust the ADR. One local model (`qwen3.8:27b`, temperature 0, seed 7), the same prompt for all model arms, which includes the verdict definitions.
- **Metrics:** verdicts right (of 90); dead decisions (MOOT or DISPUTED) called HOLDS; for those, whether a cited document is one that killed it; exact *since* date on MOOT, DISPUTED and RETIRED; false alarms on HOLDS.
- **Predictions:**
  1. Moot answers 90/90 with every *why* and *since* right. This is the common-mode ceiling (labels and graph share the spec), not a finding.
  2. RAG + model calls at least 4 of the 21 dead decisions HOLDS, and gets fewer than half of the *since* dates exactly.
  3. RAG over stated reasons does better than plain RAG on *why*, but still misses the decisions whose dead reason is two hops below the stated one (D01, D02, D03).
  4. Depth 1 calls those same decisions HOLDS on the dates after PR-412 (2026-03-02).
  5. Dates ignored: every question on 2025-06-01 and 2026-01-01 whose label differs from today's verdict is wrong, and NOT_YET is never answered.
  6. Moot rows + model is within 5 verdicts of Moot: the model can read a path without breaking it.
- **Outcome (2026-10-19, after the run):** predictions 1, 2, 5 and 6 held; 3 and 4 held for D01 only (D02 and D03 state the gateway limit directly, so neither a depth-1 audit nor a retriever over stated reasons misses them). The dead-decision denominator is 22, not the 21 written above. Details: [evaluation.md](evaluation.md#head-to-head-against-a-retrieval-company-brain-study-s3).
- **Script:** `python3 eval/eval_baseline.py --llm` (fills the model cache) then `python3 eval/eval_baseline.py` → `eval/results_baseline.md` and `.json`.

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
