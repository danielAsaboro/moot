# K3: questions about Kubernetes as an organisation (study K3)

90 templated questions about SIG Auth and SIG Node KEPs; gold from the raw git history of kubernetes/enhancements and kubernetes/community (`moot/k1.py`), hashed before any arm ran (`74641a80e72cbc77…`). Same model (qwen3.8:27b, temperature 0) for every model arm. **Shared-source caveat:** Moot's graph is built from the same files, so its fixed-query row is close to the gold by construction; the contest is between agents with the same model and different tools. Templates: (1) which KEP replaced it and when, (2) who led its SIG on a date, (3) was it in force on a date and what retired it, (4) its authors and whether each leads a SIG today.

## Test split

| arm | exact match (95% CI) | t7 | t8 | t9 | t10 | t11 | t12 | t13 | tokens | $ at Groq's price | median s per question | tool calls |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Moot, one fixed graph query per template, no model (shared-source reference) | 10/65 (0.09–0.26) | 0/11 | 0/8 | 0/6 | 8/11 | 0/11 | 2/7 | 0/11 | 0 | 0.000 | 0.0055 | 0 |


## Dev split

| arm | exact match (95% CI) | t7 | t8 | t9 | t10 | t11 | t12 | t13 | tokens | $ at Groq's price | median s per question | tool calls |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Moot, one fixed graph query per template, no model (shared-source reference) | 4/25 (0.06–0.35) | 0/4 | 0/3 | 0/3 | 3/4 | 0/4 | 1/3 | 0/4 | 0 | 0.000 | 0.0057 | 0 |


