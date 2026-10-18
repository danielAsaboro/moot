# K1: questions about Kubernetes as an organisation (study K1)

46 templated questions about SIG Auth and SIG Node KEPs; gold from the raw git history of kubernetes/enhancements and kubernetes/community (`moot/k1.py`), hashed before any arm ran (`b5b5ee1c96b319a5…`). Same model (qwen3.8:27b, temperature 0) for every model arm. **Shared-source caveat:** Moot's graph is built from the same files, so its fixed-query row is close to the gold by construction; the contest is between agents with the same model and different tools. Templates: (1) which KEP replaced it and when, (2) who led its SIG on a date, (3) was it in force on a date and what retired it, (4) its authors and whether each leads a SIG today.

## Test split

| arm | exact match (95% CI) | t1 | t2 | t3 | t4 | tokens | $ at Groq's price | median s per question | tool calls |
|---|---|---|---|---|---|---|---|---|---|
| **agent with Moot's graph tools** | 26/34 (0.60–0.88) | 1/1 | 7/11 | 8/11 | 10/11 | 131,474 | 0.042 | 11.0 | 74 |
| agent with file and git tools over the same checkouts | 22/34 (0.48–0.79) | 1/1 | 8/11 | 8/11 | 5/11 | 362,173 | 0.115 | 38.3 | 193 |
| BM25 RAG over the checkouts at HEAD | 15/34 (0.29–0.61) | 1/1 | 0/11 | 7/11 | 7/11 | 84,837 | 0.026 | 28.4 | 0 |
| BM25 RAG over the checkouts and their history (post hoc, see register) | 17/34 (0.34–0.66) | 1/1 | 0/11 | 9/11 | 7/11 | 67,031 | 0.020 | 22.8 | 0 |
| Moot, one fixed graph query per template, no model (shared-source reference) | 25/34 (0.57–0.85) | 1/1 | 6/11 | 8/11 | 10/11 | 0 | 0.000 | – | 0 |
| the same fixed query on the graph rebuilt with commit-dated SIG leadership (post hoc, product change registered before K2) | 26/34 (0.60–0.88) | 1/1 | 7/11 | 8/11 | 10/11 | 0 | 0.000 | 0.0009 | 0 |

- graph agent vs agent with file and git tools over the same checkouts: on 34 questions both answered, only the graph agent right on 8, only the other on 4; exact McNemar p = 0.388
- graph agent vs BM25 RAG over the checkouts at HEAD: on 34 questions both answered, only the graph agent right on 13, only the other on 2; exact McNemar p = 0.007
- graph agent vs BM25 RAG over the checkouts and their history (post hoc, see register): on 34 questions both answered, only the graph agent right on 11, only the other on 2; exact McNemar p = 0.022

## Dev split

| arm | exact match (95% CI) | t1 | t2 | t3 | t4 | tokens | $ at Groq's price | median s per question | tool calls |
|---|---|---|---|---|---|---|---|---|---|
| **agent with Moot's graph tools** | 11/12 (0.65–0.99) | 0/0 | 3/4 | 4/4 | 4/4 | 35,721 | 0.011 | 9.1 | 24 |
| agent with file and git tools over the same checkouts | 7/12 (0.32–0.81) | 0/0 | 2/4 | 3/4 | 2/4 | 119,612 | 0.038 | 34.3 | 66 |
| BM25 RAG over the checkouts at HEAD | 7/12 (0.32–0.81) | 0/0 | 0/4 | 4/4 | 3/4 | 30,672 | 0.009 | 30.5 | 0 |
| BM25 RAG over the checkouts and their history (post hoc, see register) | 7/12 (0.32–0.81) | 0/0 | 0/4 | 4/4 | 3/4 | 24,060 | 0.007 | 22.2 | 0 |
| Moot, one fixed graph query per template, no model (shared-source reference) | 10/12 (0.55–0.95) | 0/0 | 2/4 | 4/4 | 4/4 | 0 | 0.000 | – | 0 |
| the same fixed query on the graph rebuilt with commit-dated SIG leadership (post hoc, product change registered before K2) | 10/12 (0.55–0.95) | 0/0 | 2/4 | 4/4 | 4/4 | 0 | 0.000 | 0.0006 | 0 |

- graph agent vs agent with file and git tools over the same checkouts: on 12 questions both answered, only the graph agent right on 5, only the other on 1; exact McNemar p = 0.219
- graph agent vs BM25 RAG over the checkouts at HEAD: on 12 questions both answered, only the graph agent right on 4, only the other on 0; exact McNemar p = 0.125
- graph agent vs BM25 RAG over the checkouts and their history (post hoc, see register): on 12 questions both answered, only the graph agent right on 4, only the other on 0; exact McNemar p = 0.125

## The 16 test answers produced on qwen/qwen3.8-27b (not in the table above)

The register's amendments explain why these exist; they are listed so nothing is dropped.

| question | arm | qwen/qwen3.8-27b | qwen3.8:27b on the same question |
|---|---|---|---|
| k1-f5f572e333 (t1) | moot_tools | right | right |
| k1-f5f572e333 (t1) | file_tools | right | right |
| k1-f5f572e333 (t1) | rag_bm25 | no answer | right |
| k1-07a3bd3497 (t2) | moot_tools | wrong | no answer |
| k1-07a3bd3497 (t2) | file_tools | wrong | right |
| k1-07a3bd3497 (t2) | rag_bm25 | no answer | wrong |
| k1-0b89a1cace (t2) | moot_tools | right | right |
| k1-0b89a1cace (t2) | file_tools | wrong | no answer |
| k1-0b89a1cace (t2) | rag_bm25 | no answer | wrong |
| k1-32b58a66e3 (t2) | moot_tools | right | right |
| k1-32b58a66e3 (t2) | file_tools | wrong | right |
| k1-32b58a66e3 (t2) | rag_bm25 | no answer | wrong |
| k1-49ab39407e (t2) | moot_tools | wrong | wrong |
| k1-49ab39407e (t2) | file_tools | wrong | right |
| k1-49ab39407e (t2) | rag_bm25 | no answer | wrong |
| k1-69fd57c98b (t2) | moot_tools | right | right |

On these 16: qwen/qwen3.8-27b 5 right, qwen3.8:27b 9 right.

