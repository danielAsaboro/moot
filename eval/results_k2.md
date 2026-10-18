# K2: questions about Kubernetes as an organisation (study K2)

78 templated questions about SIG Auth and SIG Node KEPs; gold from the raw git history of kubernetes/enhancements and kubernetes/community (`moot/k1.py`), hashed before any arm ran (`6ede7d9fbde193d6…`). Same model (qwen3.8:27b, temperature 0) for every model arm. **Shared-source caveat:** Moot's graph is built from the same files, so its fixed-query row is close to the gold by construction; the contest is between agents with the same model and different tools. Templates: (1) which KEP replaced it and when, (2) who led its SIG on a date, (3) was it in force on a date and what retired it, (4) its authors and whether each leads a SIG today.

## Test split

| arm | exact match (95% CI) | t1 | t2 | t3 | t4 | t5 | t6 | tokens | $ at Groq's price | median s per question | tool calls |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Moot, one fixed graph query per template, no model (shared-source reference) | 38/57 (0.54–0.78) | 2/2 | 7/11 | 7/11 | 11/11 | 0/11 | 11/11 | 0 | 0.000 | – | 0 |


## Dev split

| arm | exact match (95% CI) | t1 | t2 | t3 | t4 | t5 | t6 | tokens | $ at Groq's price | median s per question | tool calls |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Moot, one fixed graph query per template, no model (shared-source reference) | 14/21 (0.45–0.83) | 1/1 | 2/4 | 4/4 | 3/4 | 0/4 | 4/4 | 0 | 0.000 | – | 0 |


