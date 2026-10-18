# Scaling and verdict eval

## 1. Noise scaling

The corpus is padded with N templated documents about the same systems (touching no premise). k = 5. Targets: the 16 documents that contradict a premise of the 16 MOOT/DISPUTED decisions. Seed time is the idempotent MERGE import.

| extra noise docs | documents | graph nodes / edges | seed (s) | graph recall@5 (consistency check) | BM25 recall@5 |
|---|---|---|---|---|---|
| 0 | 208 | 314 / 373 | 0.0 | **1.00** | 0.81 |
| 1,000 | 1,208 | 1,314 / 1,373 | 0.0 | **1.00** | 0.81 |
| 5,000 | 5,208 | 5,314 / 5,373 | 0.2 | **1.00** | 0.81 |
| 20,000 | 20,208 | 20,314 / 20,373 | 0.6 | **1.00** | 0.81 |

The graph column is not a retrieval result. Its targets are the CONTRADICTS edges in `truth.json`, and the graph's CONTRADICTS edges come from the same spec, so the audit reads back its own edges; 1.00 says the ingest kept every edge at every corpus size. BM25 is a real retrieval result against the same targets.

### Latency

Wall-clock from the Python client to a FalkorDB server on the same laptop, in milliseconds. *Warm* is nearest-rank p50 / p95 over n calls after 5 warmup calls were dropped (audit: every target decision, 5 rounds; ledger and trace: 20 calls). *Cold* is the first call on the freshly seeded graph, before any query plan is cached; *fresh process* is the first audit from a new Python process, including the connection but not the imports. Cold numbers are reported apart and never folded into the percentiles. Raw samples: `eval/results_scale.json`.

| extra noise docs | audit warm n · p50 / p95 | audit cold | audit, fresh process | full ledger warm n · p50 / p95 | ledger cold | SPpaths trace warm n · p50 / p95 | trace cold |
|---|---|---|---|---|---|---|---|
| 0 | 80 · 1.0 / 1.1 | 2.8 | 11.1 | 20 · 2.8 / 2.9 | 3.4 | 20 · 0.8 / 0.9 | 1.1 |
| 1,000 | 80 · 0.9 / 1.1 | 2.4 | 10.9 | 20 · 2.7 / 3.1 | 3.4 | 20 · 0.8 / 0.8 | 1.0 |
| 5,000 | 80 · 0.9 / 1.1 | 3.2 | 10.5 | 20 · 2.8 / 3.0 | 3.4 | 20 · 0.8 / 0.9 | 1.2 |
| 20,000 | 80 · 0.9 / 1.1 | 4.5 | 10.8 | 20 · 2.9 / 3.0 | 3.4 | 20 · 0.8 / 0.9 | 1.1 |

Reading it: the graph's recall is flat by construction (noise never touches a premise, and the audit walks premises, not text), and its latency is flat because the audit is an index lookup plus a bounded path expansion, independent of corpus size. BM25's recall on this templated noise also stays put: its misses are not a crowding problem but a vocabulary one, the killing document does not share words with the decision at any corpus size. The seed column is the honest cost: a labelled MERGE import of 20k documents takes about a second; an earlier unlabelled version took three minutes, which is why the import now names labels on both ends of every edge.

## 2. Verdicts against ground truth

Ground truth is the expected verdict per decision in `moot/corpus/spec.py` (30 decisions). The graph rule gets **30/30** exactly right.

Staleness detection (is the decision MOOT or DISPUTED?), compared with a retrieval-only baseline that flags a decision when a later document in its BM25 top-5 carries a change cue such as "raise", "no longer" or "roll back":

| method | precision | recall | F1 |
|---|---|---|---|
| graph path rule (Moot) | **1.00** | **1.00** | **1.00** |
| BM25 top-5 + change-cue heuristic | 0.50 | 0.75 | 0.60 |

Confusion (expected → graph):

- DISPUTED → DISPUTED: 4
- HOLDS → HOLDS: 10
- MOOT → MOOT: 12
- RETIRED → RETIRED: 1
- UNDOCUMENTED → UNDOCUMENTED: 3

## Threats to validity, worst first

1. **Common-mode targets.** The ground truth and the graph share the same spec, so the 30/30 and the graph's recall say the verdict rule and the ingest are consistent, not that extraction from raw text is solved (see `moot/ingest/extract.py`).
2. **Templated noise.** The padding documents touch no premise and share a template, so they cannot crowd the graph and only test BM25's vocabulary problem. Realistic noise that mentions the same premises would be harder for both.
3. **A shared laptop.** Latencies were measured on one machine with other work running (this run shared it with a local model job). They are good for the shape of the curve against corpus size, not as a number to quote for production.
4. **Cold is not a server restart.** The FalkorDB server was shared and not restarted, so *cold* means a fresh graph and a fresh client process; a cold server start (loading the graph from disk) is not measured.
5. **No model baseline.** The staleness baseline has no model, by design, so the whole file reproduces offline. The model-judged RAG baseline is study S3 (`eval/results_baseline.md`): BM25 RAG with a local model, 62/90 against Moot's 90/90.
