# Head-to-head: graph verdicts against a retrieval company brain

Study S3 ([docs/studies.md](../docs/studies.md)), registered before it ran. 90 questions: each of Larkspur's 30 decisions on 3 dates (2025-06-01, 2026-01-01, 2026-10-16), asked *does it still hold, which documents show it, since when?* Labels were frozen from `truth.json` alone (`eval/baseline/questions.json`, `eval/baseline_questions.py`) with a verdict rule written independently of `moot/verdict.py`. Model arms use the same local model, prompt and decoding (`qwen3.8:27b`, temperature 0, seed 7); only the context differs.

| arm | verdicts right (of 90) | dead decisions called HOLDS (of 22) | cited a document that killed it (of 22) | "since when" exact (of 24) | false alarms on HOLDS (of 50) |
|---|---|---|---|---|---|
| **Moot** (graph verdict, depth 4) | **90** | **0** | **22** | **24** | 0 |
| Moot rows + model (the graph's path, narrated) | 89 | 0 | 22 | 18 | 0 |
| RAG: BM25 top-5 + model | 62 | 13 | 9 | 8 | 1 |
| RAG over stated reasons + model (FalkorDB removed) | 76 | 7 | 16 | 12 | 0 |
| ablation: depth 1 | 88 | 2 | 20 | 22 | 0 |
| ablation: no as_of (dates ignored) | 62 | 0 | 22 | 23 | 20 |
| ablation: FalkorDB removed, rules kept | 60 | 8 | 10 | 10 | 16 |
| trust the ADR | 56 | 22 | 0 | 0 | 0 |

Verdicts right, by date:

| arm | 2025-06-01 | 2026-01-01 | 2026-10-16 |
|---|---|---|---|
| **Moot** (graph verdict, depth 4) | 30/30 | 30/30 | 30/30 |
| ablation: depth 1 | 30/30 | 30/30 | 28/30 |
| ablation: no as_of (dates ignored) | 13/30 | 19/30 | 30/30 |
| ablation: FalkorDB removed, rules kept | 26/30 | 20/30 | 14/30 |
| trust the ADR | 25/30 | 21/30 | 10/30 |
| RAG: BM25 top-5 + model | 22/30 | 22/30 | 18/30 |
| RAG over stated reasons + model (FalkorDB removed) | 25/30 | 27/30 | 24/30 |
| Moot rows + model (the graph's path, narrated) | 29/30 | 30/30 | 30/30 |

## Threats to validity, worst first

1. **Common-mode answer key.** The Moot arms read a graph built from the same spec as the labels, so their scores measure what the path rules and dated edges do *given* correct edges, an upper bound for Moot. The retrieval arms read the raw documents. The question this answers is what a retrieval brain loses against a correctly built graph, not whether extraction builds one.
2. **Small and synthetic.** 90 questions about 30 decisions in an invented company, and the dates share decisions, so the questions are not independent.
3. **One local model, one run.** The model arms ran once on a local open-weights model; answers are cached in `eval/baseline/llm_cache.jsonl` so the scores re-derive exactly, but a stronger model would likely do better on both sides of the comparison.
4. **The retrieval arms get the rule definitions in the prompt**, which a real doc-chat brain would not have. That favours them.
