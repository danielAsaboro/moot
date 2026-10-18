# K2: questions about Kubernetes as an organisation (study K2)

78 templated questions about SIG Auth and SIG Node KEPs; gold from the raw git history of kubernetes/enhancements and kubernetes/community (`moot/k1.py`), hashed before any arm ran (`6ede7d9fbde193d6…`). Same model (qwen3.8:27b, temperature 0) for every model arm. **Shared-source caveat:** Moot's graph is built from the same files, so its fixed-query row is close to the gold by construction; the contest is between agents with the same model and different tools. Templates: (1) which KEP replaced it and when, (2) who led its SIG on a date, (3) was it in force on a date and what retired it, (4) its authors and whether each leads a SIG today.

## Test split

| arm | exact match (95% CI) | t1 | t2 | t3 | t4 | t5 | t6 | tokens | $ at Groq's price | median s per question | tool calls |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **agent with Moot's graph tools** | 41/57 (0.59–0.82) | 2/2 | 10/11 | 7/11 | 11/11 | 0/11 | 11/11 | 189,181 | 0.060 | 10.9 | 117 |
| agent with file and git tools over the same checkouts | 22/57 (0.27–0.52) | 2/2 | 6/11 | 7/11 | 6/11 | 0/11 | 1/11 | 723,781 | 0.229 | 40.5 | 271 |
| BM25 RAG over the checkouts at HEAD | 26/57 (0.33–0.58) | 0/2 | 0/11 | 9/11 | 9/11 | 1/11 | 7/11 | 131,478 | 0.040 | 25.8 | 0 |
| BM25 RAG over the checkouts and their history (post hoc, see register) | 27/57 (0.35–0.60) | 2/2 | 0/11 | 9/11 | 9/11 | 1/11 | 6/11 | 84,654 | 0.026 | 16.6 | 0 |
| Moot, one fixed graph query per template, no model (shared-source reference) | 38/57 (0.54–0.78) | 2/2 | 7/11 | 7/11 | 11/11 | 0/11 | 11/11 | 0 | 0.000 | 0.0008 | 0 |

- graph agent vs agent with file and git tools over the same checkouts: on 57 questions both answered, only the graph agent right on 22, only the other on 3; exact McNemar p < 0.001
- graph agent vs BM25 RAG over the checkouts at HEAD: on 57 questions both answered, only the graph agent right on 18, only the other on 3; exact McNemar p = 0.001
- graph agent vs BM25 RAG over the checkouts and their history (post hoc, see register): on 57 questions both answered, only the graph agent right on 17, only the other on 3; exact McNemar p = 0.003

## Dev split

| arm | exact match (95% CI) | t1 | t2 | t3 | t4 | t5 | t6 | tokens | $ at Groq's price | median s per question | tool calls |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **agent with Moot's graph tools** | 13/21 (0.41–0.79) | 1/1 | 2/4 | 3/4 | 3/4 | 0/4 | 4/4 | 89,844 | 0.028 | 13.1 | 45 |
| agent with file and git tools over the same checkouts | 12/21 (0.37–0.76) | 1/1 | 3/4 | 3/4 | 4/4 | 0/4 | 1/4 | 284,835 | 0.091 | 55.2 | 112 |
| BM25 RAG over the checkouts at HEAD | 10/21 (0.28–0.68) | 1/1 | 0/4 | 4/4 | 3/4 | 0/4 | 2/4 | 49,284 | 0.015 | 25.5 | 0 |
| BM25 RAG over the checkouts and their history (post hoc, see register) | 10/21 (0.28–0.68) | 1/1 | 0/4 | 4/4 | 3/4 | 0/4 | 2/4 | 31,181 | 0.009 | 17.8 | 0 |
| Moot, one fixed graph query per template, no model (shared-source reference) | 14/21 (0.45–0.83) | 1/1 | 2/4 | 4/4 | 3/4 | 0/4 | 4/4 | 0 | 0.000 | 0.0008 | 0 |

- graph agent vs agent with file and git tools over the same checkouts: on 21 questions both answered, only the graph agent right on 4, only the other on 3; exact McNemar p = 1.0
- graph agent vs BM25 RAG over the checkouts at HEAD: on 21 questions both answered, only the graph agent right on 5, only the other on 2; exact McNemar p = 0.453
- graph agent vs BM25 RAG over the checkouts and their history (post hoc, see register): on 21 questions both answered, only the graph agent right on 5, only the other on 2; exact McNemar p = 0.453

