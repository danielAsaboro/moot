# Retrieval eval: finding the evidence that kills a premise

Decisions with at least one invalidating document (ground truth MOOT or DISPUTED): **16**. k = 5. Corpus: 208 non-ADR documents.

| method | recall@5 of invalidating docs | decisions with ≥1 found |
|---|---|---|
| graph path query (Moot) | **1.00** | **100%** |
| BM25 top-5, query = decision title + summary | 0.81 | 81% |
| random 5 docs (control, mean of 20 seeds) | 0.01 | – |

Why BM25 misses: the invalidating document rarely shares words with the decision. "Cap file uploads at 10 MB" is killed by "Raise the API gateway body limit to 100 MB", two premise hops away; "Keep the monolith" is killed by all-hands notes about headcount. Lexical and semantic similarity find documents *about* the decision; the graph finds documents about its *reasons*.

| decision | targets | graph | bm25 | bm25 top-5 |
|---|---|---|---|---|
| D01 Cap file uploads at 10 MB | PR-412 | 100% | 100% | PR-412, doc-handbook-deploys, OPS-954, PR-488, doc-logcost-2026 |
| D02 Chunk CSV imports into 5 MB parts | PR-412 | 100% | 100% | PR-412, doc-vendor-rn, PR-1034, PR-923, OPS-1008 |
| D03 Reject photos over 8 MB in the mobile app | PR-412 | 100% | 100% | PR-412, PR-964, PR-1007, PR-935, chat-noise-973 |
| D04 Rebuild the search index in full every night | SRCH-233 | 100% | 100% | chat-2025-10-02-search, SRCH-233, PR-959, PR-971, PR-988 |
| D07 Freeze production deploys on Fridays | PR-350 | 100% | 100% | PR-350, PR-398, doc-handbook-deploys, chat-2026-01-08-standup, PR-1039 |
| D08 Keep the monolith; no new services | doc-allhands-2026-04 | 100% | 0% | PR-430, chat-2026-05-16-farewell, SRCH-233, doc-vendor-rn, PR-488 |
| D09 Serve EU customers from Frankfurt only | SALES-91 | 100% | 100% | doc-aws-cmk, PR-950, SALES-91, doc-privacy-2026, BILL-77 |
| D11 Require two reviewers on every pull request | PR-201 | 100% | 100% | PR-201, chat-2026-02-26-hiring, doc-oncall-2026, PR-520, doc-allhands-2026-04 |
| D13 Encrypt PII in the application layer | doc-aws-cmk | 100% | 100% | doc-aws-cmk, chat-2026-06-05-retro, PR-398, PR-430, PR-455 |
| D17 Use LaunchDarkly for feature flags | chat-2026-07-09-ld | 100% | 0% | DATA-150, OPS-1032, chat-2026-08-15-ld, OPS-969, PR-1004 |
| D18 Manual QA sign-off before every release | PR-520 | 100% | 100% | PR-520, PR-350, doc-vendor-rn, doc-handbook-deploys, PR-430 |
| D19 Run the data pipeline hourly, not continuously | DATA-140 | 100% | 0% | PR-471, PR-999, OPS-1000, chat-noise-944, chat-noise-1041 |
| D20 Pin the mobile app to React Native 0.72 | doc-vendor-rn | 100% | 100% | doc-vendor-rn, chat-noise-913, chat-noise-921, chat-noise-987, chat-noise-940 |
| D23 Use UUIDv4 for every primary key | ADR-notes-sharding | 100% | 100% | ADR-notes-sharding, doc-aws-cmk, doc-okr-2026-h2, PR-520, PR-471 |
| D25 Disable public sign-ups | doc-abuse-2026-06 | 100% | 100% | doc-abuse-2026-06, PR-520, chat-2025-08-21-ci, chat-2026-05-16-farewell, SRCH-233 |
| D30 Block third-party cookies in the embed widget | doc-news-cookies | 100% | 100% | doc-news-cookies, doc-logcost-2026, chat-noise-1022, PR-1045, chat-noise-1031 |

Limits: the corpus is synthetic and small; BM25 is a strong but not state-of-the-art baseline (no embeddings, by design, so the number reproduces without a model); a retriever given the *premise text* instead of the decision would do better, but a RAG system does not know the premise exists. That is the point.
