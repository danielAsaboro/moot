# H2: a fresh held-out set, the product gate policy (study H2)

22 decisions from repositories outside the backtest and H1, in force on 2022-10-17, graded on 2025-10-17 by the H1 rule; gold hashed before any arm ran (`ca6d3920ceb83cf4…`). **Underpowered:** 1 decision died, so balanced accuracy, the registered primary metric, swings on one call. Run once, as registered.

## Test split (16 decisions, 1 DEAD)

| arm | balanced accuracy (primary) | right | DEAD caught | held decisions called DEAD (blocked) | vs Moot (only Moot right / only it right, p) |
|---|---|---|---|---|---|
| **Moot gate, product policy (warn)** | 0.50 | 15/16 | 0/1 | 0/15 | – |
| majority class (dev) | 0.50 | 15/16 | 0/1 | 0/15 | 0 / 0, p = 1.000 |
| trust the ADR's status | 0.50 | 15/16 | 0/1 | 0/15 | 0 / 0, p = 1.000 |
| age ≥ 3 years | 0.87 | 12/16 | 1/1 | 4/15 | 4 / 1, p = 0.375 |
| BM25 RAG + qwen3.8:27b | 0.50 | 15/16 | 0/1 | 0/15 | 0 / 0, p = 1.000 |
| LLM agent with GitHub/OSV tools (openai/gpt-oss-20b) | 0.43 | 13/16 | 0/1 | 2/15 | 2 / 0, p = 0.500 |

All 22 decisions (dev and test; nothing was tuned on dev): Moot gate, product policy (warn) 21/22 right, 0/1 caught, 0 false alarms, majority class (dev) 21/22 right, 0/1 caught, 0 false alarms, trust the ADR's status 21/22 right, 0/1 caught, 0 false alarms, age ≥ 3 years 14/22 right, 1/1 caught, 8 false alarms, BM25 RAG + qwen3.8:27b 21/22 right, 0/1 caught, 0 false alarms, LLM agent with GitHub/OSV tools (openai/gpt-oss-20b) 19/22 right, 0/1 caught, 2 false alarms.
