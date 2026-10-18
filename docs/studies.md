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

- **Written:** 2026-10-18 06:58 UTC, after a hand count of the effect (ALLOW 10 → 4), before `eval/eval_gate.py` was re-run.
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

## H1. Held-out: does a real decision still hold, graded by what its repository later did

- **Written:** 2026-10-21 07:05 UTC, after the gold was built and hashed and before any arm ran on it; revised 07:20 UTC, still before any arm ran, to drop units whose ADR was not yet committed on T0 (an imported repository, whose code on T0 does not exist). The gold builder was run for three candidate cut dates (T0 = 2021-, 2022-, 2023-10-17) to count labels only (7, 6 and 7 DEAD); 2023-10-17 was kept because it gives the most units. One thing was public before the gold existed: the backtest's monthly gate calls (`data/backtest/gates.json`) on the 70 units that come from the backtest. The gold builder never reads them.
- **Question:** seeing only what existed on T0 = 2023-10-17, does each decision still hold? Graded on 2026-10-17 by sources nobody on this project wrote.
- **Units:** every ADR whose title picks an outside tool (the backtest's catalogue, plus `moot/heldout/tools.py`, written from titles alone, for decisions from 32 public repositories outside the backtest) and that is in force and committed to its repository on T0 (an ADR imported later is out, whatever date it carries). 92 units: 70 reused from the backtest, 22 new.
- **Gold** (`moot/heldout/gold.py`, mechanical): DEAD if, after T0 and by 2026-10-17, the repository marked the ADR superseded or deprecated, moved it to an archive folder, a later ADR's title dropped its tool, or the tool left the repository's dependency manifests or Terraform. HOLDS otherwise, backed by the tool still being in the code (60) or, where the code has no signal for that tool, only by the unchanged status (31). 10 units the code cannot grade (the tool was not in the code on T0) are left out. 7 DEAD, 85 HOLDS.
- **Split:** within each gold class, sorted by sha256(id); the first 30% are dev (2 DEAD, 26 HOLDS), the rest test (5 DEAD, 59 HOLDS). `eval/heldout/gold.json` carries a sha256 over (T0, END, units, labels, split), pinned in `eval/heldout/GOLD.sha256`; `eval/eval_heldout.py` refuses to score if either differs.
- **Arms:** Moot's gate (DENY = DEAD) in a FalkorDB graph built like the backtest's; the same verdict rules with FalkorDB removed (BM25 top 3 evidence documents for the ADR); the dev split's majority class; the age rule (3 years); trust the ADR's status (in force on T0 for every unit, so HOLDS); BM25 RAG + local qwen3.8:27b (top 5 of the repository's other ADRs and the tool evidence); an LLM agent (Groq openai/gpt-oss-20b; registered as gpt-oss-120b, switched at 07:55 UTC before any test unit ran because the free tier's 200,000 tokens a day for 120b were spent on the router eval) with tools for the ADR, the repository's ADRs, GitHub activity, licence history and OSV advisories, all cut at T0. Every arm sees ADR text with its Status section removed.
- **Metrics:** accuracy with 95% Wilson intervals on the test split, DEAD recall and precision, balanced accuracy, and exact McNemar tests against Moot on paired right/wrong outcomes; the agent's tokens, dollars and model latency.
- **Predictions, written before any arm ran:**
  1. No arm beats the majority class (HOLDS for everything) on accuracy by more than the interval: with 5 DEAD in 64 test units, HOLDS-for-all is right about 92% of the time.
  2. Moot catches at most 2 of the 5 test DEAD: outside evidence sees tool deaths, and most of these died in the code, not upstream.
  3. Most of Moot's DEAD calls are HOLDS by this gold (Terraform's 2023 licence change, quiet upstream repositories the teams still use), so its precision is below 0.3. The backtest's reading calls those flags real; this gold, by design, does not.
  4. The tool-using agent and Moot land within each other's intervals; the agent costs dollars and seconds per decision, Moot costs neither.
- **Script:** `python3 -m moot.heldout.gold` (labels), `python3 -m moot.heldout.inputs` (what arms may see), `python3 eval/eval_heldout.py --llm` → `eval/results_heldout.md` and `.json`.

## P1. Precision of flags on real history, graded by what the repositories later did

- **Written:** 2026-10-21 07:50 UTC, before `eval/eval_precision.py` existed or ran. Moot's monthly gate calls on the backtest (`data/backtest/gates.json`) and its own reading of the 22 flags (`eval/results_backtest.md`) were public before this entry; the grading below never reads that reading.
- **Question:** when a method raises a flag on a real decision its repository still lists as in force, how often did the repository later abandon that decision?
- **Units:** flags. A method's flag on a decision is the first month it calls the decision dead while the decision is in force: Moot's gate DENY (`data/backtest/gates.json`), the age rule on the decision's third anniversary, a random flagger with Moot's budget (200 seeds), trust the ADR (never flags). The 97 tool decisions of the backtest. Only flags raised on or before 2023-10-17 count, so every flag has a full three-year window before the 2026-10-17 snapshot.
- **Gold, one procedure fixed in advance (the H1 rule, `moot/heldout/gold.py`):** a flag is confirmed if, within three years after it, the repository changed the ADR's status to superseded or deprecated, moved it to an archive folder, titled a later ADR as dropping the tool, or the tool left the repository's dependency manifests or Terraform (in the code on the flag's date, gone three years later or at the snapshot). Otherwise it is unconfirmed. A flag on a decision whose tool has no code signal and whose status never changed is unconfirmed.
- **Metrics:** precision (confirmed / flags) with 95% Wilson intervals; flags per confirmed death; median lead time from flag to the repository's own change.
- **Predictions:**
  1. Moot's precision is higher than the age rule's, but the intervals overlap: both are small.
  2. Moot's flags per confirmed death is lower than the age rule's.
  3. Most of Moot's flags stay unconfirmed: teams keep using Terraform after its licence change, and quiet upstream libraries stay in manifests. Precision stays below 0.3.
  4. Moot's median lead time is longer than a year when it is confirmed at all.
- **Script:** `python3 eval/eval_precision.py` → `eval/results_precision.md` and `.json`.

## A1. Agent effectiveness on real decisions: what would an agent have been allowed to do?

- **Written:** 2026-10-21 07:50 UTC, while H1's test arms were still running and before this tally was computed. It reuses H1's frozen gold and split, so nothing new is labelled.
- **Question:** an agent asks before acting on each H1 decision on 2023-10-17. How many actions on decisions that later died does each gatekeeper ALLOW, and how many actions on decisions that held does it block?
- **Arms:** Moot's gate (ALLOW; DENY and REVALIDATE block), trust the ADR (allows all), the age rule (blocks at 3 years), BM25 RAG and the LLM agent from H1 (HOLDS allows, DEAD blocks).
- **Metrics, on H1's test split:** dead decisions allowed (of 5), held decisions blocked (of 59), each with Wilson intervals. The two pull against each other and are reported side by side, never summed.
- **Predictions:** Moot allows 0 of the dead decisions and blocks most of the held ones (REVALIDATE: no dated evidence either way); trust the ADR allows all 5; the age rule and the model arms fall between.
- **Script:** part of `eval/eval_heldout.py` (`results_heldout.json` → `agent_gate`).

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

## R1. Stated reasons from ADR text (descriptive, not a study)

- **Written:** 2026-10-19 17:00 UTC, after the connector's UNDOCUMENTED counts were seen (adr-tools 9 of 9, govuk-aws 21 of 31, govuk-infrastructure 11 of 24, log4brains 5 of 11) and after a trial on adr-tools changed the extraction prompt once (the first prompt returned no reasons for ADRs whose Context plainly states them). So this is a before/after description, not a registered test: there is no labelled set of real reasons to score extraction against.
- **What it reports:** verdict and gate counts per repository, built twice on the same day with the same checks and rules (titles only, then with stated reasons); what the validator kept and dropped; every decision whose verdict or gate changed.
- **What would make it look better than it is:** counting UNDOCUMENTED → HOLDS as progress. The report therefore splits HOLDS into checked (gate ALLOW) and unevidenced (REVALIDATE).
- **Script:** `python3 eval/eval_reasons.py` (model calls only on a cache miss; `--cached` reads `data/github/*/reasons.json` only) → `eval/results_reasons.md` and `.json`.
