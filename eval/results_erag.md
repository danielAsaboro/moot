# EnterpriseRAG-Bench: a blind supersession graph against Canon's oracle

**Superseded gold document still in the 10-document context (20 conflict questions, lower is better): Moot blind 13/20 · ORACLE (Canon's setup) 1/20 · BM25 baseline 14/20.**

Built blind, the graph removes the superseded document in 1 of the 14 conflicts where BM25 leaks it. Canon removes it in 13, but only because its graph was seeded from an inventory written by reading each question's gold documents and gold answer. A second, post-hoc rule set (v2) also caught 1. We report this as measured. The rules are precise but have almost no recall on how this benchmark phrases its conflicts (see *Why the blind rules miss*).

## What each arm may read

- **Moot blind** reads question text, the BM25 ranking it produces, and the text of the 50 documents ranked for each question. It never reads `expected_doc_ids`, `gold_answer` or `answer_facts`. `tests/test_erag.py` fails if any blind module names a gold field, or if the blind path asks the questions file for any column other than `question_id` and `question`. Both checks were mutation-tested: each fails when the blind path is made to read the answer key.
- **ORACLE** reproduces Canon (github.com/Enoch208/canon). It drops the retired gold document named in Canon's `research/conflict_inventory.json`, pins the current one, and leaves the one contested claim (qst_0413) alone. Its contexts match Canon's published `canon_filtered` contexts on 20/20 questions.
- Every arm answers from exactly 10 documents of the same BM25 ranking: SQLite FTS5, bm25(title 2.0, content 1.0), the question's terms OR-ed. This reproduces Canon's baseline top-10 on 20/20 conflict questions. Removals are backfilled from the same ranking. Context documents over all 500 questions: 5000 in every arm.

## Deterministic (no model)

| | BM25 baseline | Moot blind v1 (frozen) | random, v1 count | Moot blind v2 (post-hoc) | random, v2 count | Moot blind v3, local LLM (post-hoc) | random, v3 count | Moot blind v3-groq, Groq LLM (post-hoc) | random, v3-groq count | Moot blind v3, local qwen3.8:27b (post-hoc) | random, v3 qwen3.8 count | ORACLE, drop only | ORACLE: Canon's setup (drop + pin) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Superseded gold doc in context, conflicts (lower is better) | 14/20 | 13/20 | 14/20 | 13/20 | 14/20 | 13/20 | 14/20 | 12/20 | 14/20 | 12/20 | 14/20 | 1/20 | 1/20 |
| Current gold doc in context, conflicts | 18/20 | 18/20 | 18/20 | 18/20 | 18/20 | 18/20 | 18/20 | 18/20 | 18/20 | 18/20 | 18/20 | 18/20 | 20/20 |
| Conflict contexts changed | 0/20 | 1/20 | 1/20 | 1/20 | 1/20 | 1/20 | 1/20 | 2/20 | 2/20 | 2/20 | 2/20 | 13/20 | 15/20 |
| info_not_found contexts changed | 0/20 | 0/20 | 0/20 | 0/20 | 0/20 | 0/20 | 0/20 | 2/20 | 2/20 | 1/20 | 1/20 | 0/20 | 0/20 |
| Other questions: contexts changed | 0/460 | 7/460 | 7/460 | 18/460 | 18/460 | 4/28 (partial 28/460) | 4/28 (partial 28/460) | 0/1 (partial 1/460) | 0/1 (partial 1/460) | 9/460 | 9/460 | 0/460 | 0/460 |
| Other questions: documents removed | 0 | 11 | 11 | 26 | 26 | 4 (partial 28/460) | 4 (partial 28/460) | 0 (partial 1/460) | 0 (partial 1/460) | 9 | 9 | 0 | 0 |
| Other questions: expected documents removed | 0 | 1 | 1 | 2 | 3 | 0 (partial 28/460) | 0 (partial 28/460) | 0 (partial 1/460) | 0 (partial 1/460) | 1 | 0 | 0 | 0 |
| Other questions losing an expected document | 0/460 | 1/460 | 1/460 | 2/460 | 2/460 | 0/28 (partial 28/460) | 0/28 (partial 28/460) | 0/1 (partial 1/460) | 0/1 (partial 1/460) | 1/460 | 0/460 | 0/460 | 0/460 |

"Other questions" are the 460 that are neither `conflicting_info` nor `info_not_found`. Random arms remove the same number of top-10 documents as the Moot arm they shadow, seeded per question.

## What v1, v2 and v3 caught

- **v1** (`rules-v1`, frozen before its first run on any benchmark pool) caught qst_0411. It drops a document only when another retrieved document retires the exact value it states: *"changed from X to Y"*, *"Y (previously X)"*, *"X → Y"*, *"instead of X"*, on a line sharing three topic words and the same identifiers, and only if the older document is not dated later. Caveat: qst_0411's spans are the one conflict example we had seen in Canon's inventory while confirming the oracle, before writing v1.
- **v2** (`rules-v2-posthoc`, written after v1 was scored, frozen before its own run, still blind) caught qst_0411. On top of v1 it pairs lines in two documents that state the same claim (shared topic words, identifiers, proper nouns, the words just before the value, and every entity the question names) with different values, and lets update language or the later date decide. It found nothing new on the conflicts. It changed 18 other contexts and removed 2 expected documents.
- **v3** (`rules-v3-llm-posthoc`, written after v1 and v2 were scored, frozen before its own run, still blind) caught qst_0419. A local model (qwen2.5:14b-instruct, temperature 0) reads each question's top-10 documents and reports the value each gives, its status (current, superseded, proposed), any value it says it replaces, and its date. Rules decide the drop, and only when exactly two distinct values are present. The run was stopped at Daniel's call. The model read the 40 scored questions and 28 of the other 460, so v3's harm is partial (28/460): 4 contexts changed, 0 expected documents removed. Post-hoc diagnosis: the model often reports no value for the retired document even when the current one says what it replaced, and the two-value rule blocks conflicts where other documents add values.
- **v3-groq** (`rules-v3-llm-posthoc+groq`, post-hoc, still blind) is v3's prompt and v3's pairing rules, unchanged, with the model swapped for `qwen/qwen3.8-27b` on Groq (temperature 0, JSON mode). It caught qst_0419, qst_0423: superseded gold in context 12/20, current gold in context 18/20, info_not_found 2/20 changed. The model read the 40 scored questions and 1 of the other 460, so its harm is partial (1/460) until the free tier's daily cap lets the rest through: 0 contexts changed, 0 expected documents removed. Responses are cached in `erag-data/v3_groq_cache`; `python3 eval/erag_v3_fill.py groq --cut` resumes.
- **v3, local qwen3.8** (`rules-v3-llm-posthoc+qwen3.8-local`, post-hoc, still blind) is v3's prompt and rules, unchanged, with `qwen3.8:27b` (ollama's nvfp4 MLX build) on this machine, thinking off, temperature 0. It caught qst_0419, qst_0423: superseded gold in context 12/20, current gold in context 18/20, info_not_found 1/20 changed. The model read 460 of the other 460, so its harm covers all 460 other questions: 9 contexts changed, 1 expected documents removed. Cache: `erag-data/v3_local38_cache`; `python3 eval/erag_v3_fill.py local38 --cut` resumes.
- Harm, v1: 7/460 other contexts changed, 11 documents removed, 1 of them expected (qst_0372). info_not_found: 0/20 changed. Each removal and the sentence that justified it is in `erag-data/blind_cut.json` (`proof`).

## Why the blind rules miss (post-hoc, reads the answer key)

In all 14 conflicts where BM25 leaks the retired document, the current document is also in the top 10 (13 of them at rank 1). So retrieval is not the bottleneck: both sides of the conflict are in front of the graph. The extraction is. Only 4 of the 14 current documents repeat the retired value verbatim, which is what v1's explicit rules need. Only 4 of the retired values are a single number, which is what v2's same-claim pairing needs. The rest are tiers (*"50 / 120 / 220 QPS"*), names (*"GPG signatures"*), endpoints, or procedures. Catching those blind takes claim extraction that understands the sentence (an LLM pass), not value matching. Per question: `evidence/erag_deterministic.json` → `failure_analysis`.

## Canon's 82.5% and the judge

Canon reports 28/40 → 33/40 on the official scorer (judge `claude-sonnet-4-6`, one run). Its own published files show:
- All 20 `info_not_found` questions have byte-identical contexts and byte-identical answers in `baseline`, `canon` and `canon_filtered`. The judge still scored them 13, 13 and 15/20. It disagreed with itself on 8 of the 20 identical answers.
- Only 15 of 40 contexts differ between baseline and `canon_filtered`. Those questions account for +2 of the +5. The other +3 come from questions whose context did not change, +2 of them where the answer did not change either.
- The harness scores a failed judge call as incorrect, and its judge samples with thinking at temperature 1. A single judged run cannot separate a 2-question effect from this noise. That is why the judged protocol below is three runs plus a paired bootstrap.

## Answer level (model-judged): not run

This run was deterministic only (no `--answer --judge`, and no `ANTHROPIC_API_KEY` on the machine), so no answers were generated and nothing was judged. Every number above is deterministic. To run the answer level (answer model `claude-sonnet-5` with Canon's prompt, official judge `claude-sonnet-4-6` through `metrics_based_eval --no-correction --parallelism 2`, 3 judge runs per arm, per-type correctness with ranges, empty verdicts counted, paired bootstrap 95% interval on each arm's delta against the baseline), use a checkout of github.com/onyx-dot-app/EnterpriseRAG-Bench at `../erag-harness`:

```bash
ANTHROPIC_API_KEY=... python3 eval/eval_erag.py --answer --judge   # or: make erag-judged
```

## Reproduce

```bash
make db                 # FalkorDB on :6379
make erag               # fetch (1.4 GB, pinned revision) -> FTS5 index -> pools -> graphs `erag` (v1) and `erag_v2` -> this file
python3 -m pytest tests/test_erag.py
```

Hashes of the dataset files, pools, cuts, contexts and extractors, plus the freeze record, are in `evidence/run_manifest.json`.
