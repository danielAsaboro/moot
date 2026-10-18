# X1: HERB (dev: CollaborateForce)

Answer model and judge: qwen3.8:27b (local, temperature 0). Judge: HERB's code/evaluate.py, its prompts and scoring. Content is HERB's 0 to 100 Likert score; people, customer and artifact are F1 x 100; Avg is their mean.

| arm | Content | People | Customer | Artifact | **Avg** | unanswerable declined | answered | tokens per answer | median s |
|---|---|---|---|---|---|---|---|---|---|
| graph | 88.3 | – | – | – | **88.3** | 83.3% | 24 | 29,561 | 107.0 |
| search | 32.1 | – | – | – | **32.1** | 58.3% | 24 | 53,020 | 152.5 |
| rag | 22.1 | – | – | – | **22.1** | 25.0% | 24 | 1,755 | 30.0 |

Graph agent minus search-only agent, Avg: +56.2 (paired bootstrap 95% interval +20.0 to +85.4, 10,000 resamples within category).
