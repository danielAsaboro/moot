# Scaling and verdict eval

## 1. Noise scaling

The corpus is padded with N templated documents about the same systems (touching no premise). k = 5. Targets: the 16 documents that contradict a premise of the 16 MOOT/DISPUTED decisions. Latencies are wall-clock from the Python client to an embedded FalkorDB on one laptop core; seed time is the idempotent MERGE import.

| extra noise docs | documents | graph nodes / edges | seed (s) | graph recall@5 | BM25 recall@5 | audit p50 (ms) | full ledger (ms) | SPpaths trace (ms) |
|---|---|---|---|---|---|---|---|---|
| 0 | 208 | 314 / 373 | 0.0 | **1.00** | 0.81 | 1.0 | 3 | 1.3 |
| 1,000 | 1,208 | 1,314 / 1,373 | 0.0 | **1.00** | 0.81 | 1.1 | 3 | 1.2 |
| 5,000 | 5,208 | 5,314 / 5,373 | 0.2 | **1.00** | 0.81 | 1.1 | 9 | 2.4 |
| 20,000 | 20,208 | 20,314 / 20,373 | 0.6 | **1.00** | 0.81 | 1.1 | 3 | 1.2 |

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

Limits: synthetic corpus; the baseline has no model, by design, so the whole file reproduces offline. A model-judged RAG baseline is in `eval/eval_e2e.py` and needs an API key. The ground truth and the graph share the same spec, so the 30/30 says the verdict rule and the ingest are consistent, not that extraction from raw text is solved (see `moot/ingest/extract.py`).
