# K1: questions about Kubernetes as an organisation (study K1)

46 templated questions about SIG Auth and SIG Node KEPs; gold from the raw git history of kubernetes/enhancements and kubernetes/community (`moot/k1.py`), hashed before any arm ran (`b5b5ee1c96b319a5…`). Same local model (qwen3.8:27b, temperature 0) for every model arm. **Shared-source caveat:** Moot's graph is built from the same files, so its fixed-query row is close to the gold by construction; the contest is between agents with the same model and different tools. Templates: (1) which KEP replaced it and when, (2) who led its SIG on a date, (3) was it in force on a date and what retired it, (4) its authors and whether each leads a SIG today.

## Test split

| arm | exact match (95% CI) | t1 | t2 | t3 | t4 | tokens | median s per question | tool calls |
|---|---|---|---|---|---|---|---|---|
| Moot, one fixed graph query per template, no model (shared-source reference) | 25/34 (0.57–0.85) | 1/1 | 6/11 | 8/11 | 10/11 | 0 | – | 0 |

## Dev split

| arm | exact match (95% CI) | t1 | t2 | t3 | t4 | tokens | median s per question | tool calls |
|---|---|---|---|---|---|---|---|---|
| **agent with Moot's graph tools** | 9/12 (0.47–0.91) | 0/0 | 3/4 | 4/4 | 2/4 | 43,544 | 17.7 | 26 |
| agent with file and git tools over the same checkouts | 5/12 (0.19–0.68) | 0/0 | 0/4 | 3/4 | 2/4 | 41,532 | 24.4 | 38 |
| BM25 RAG over the checkouts at HEAD | 0/12 (0.00–0.24) | 0/0 | 0/4 | 0/4 | 0/4 | 30,672 | 31.4 | 0 |
| Moot, one fixed graph query per template, no model (shared-source reference) | 10/12 (0.55–0.95) | 0/0 | 2/4 | 4/4 | 4/4 | 0 | – | 0 |

