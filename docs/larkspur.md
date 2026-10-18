# Larkspur, the demo company

An 8-person synthetic company whose answer key comes from the same spec as its graph: a consistency ceiling, not a test of prediction.

## In 40 seconds

Ask **"Why do we cap uploads at 10 MB?"** A doc-chat brain finds the ADR and says: because the gateway rejects bodies over 10 MB. Moot answers **MOOT**:

```
D01 Cap file uploads at 10 MB
 └─BECAUSE_OF→ "All file uploads pass through the API gateway"
                └─DERIVED_FROM→ "The API gateway enforces a 10 MB request body limit"
                                 ←CONTRADICTS─ PR-412, 2026-03-02 "Raise the API gateway body limit to 100 MB"
owner: Ada Okafor, left 2026-05-15 · D02 and D03 rest on the same dead reason
```

- Flip **depth 1 → 4**: at depth 1 the verdict is HOLDS, because the stated reason is intact. The dead reason is two hops down. That hop is what a graph buys you.
- Set **as of 2025-06-01**: HOLDS again, because PR-412 did not exist yet. Every edge is dated.
- Ask an agent's question, **"may I enforce D01?"** (`GET /api/gate/D01`, or the MCP tool `check_action`): **DENY**, with the path to PR-412.
- Ask **since when**: MOOT since 2026-03-02, after HOLDS from 2025-02-10. Moot re-audits on every date something in the decision's graph happened.
- Ask **who knows why**: Marcus Chen, who wrote PR-412, and Ada Okafor, the owner, who left. Bus factor 1. **What leaves with Marcus?** Five live decisions nobody else here can explain, five reasons only he wrote evidence on, and the Uploads API.
- Point it at a real repository: `moot ingest-github thomvaill/log4brains` reads its ADR folder, git history and pull requests into a new graph, reads the reasons each ADR states in its own words (kept only as exact quoted spans), and audits every decision against GitHub, OSV and the repository's later ADRs.

Verdicts are FalkorDB path queries. The model only narrates and proposes quotes; every id it cites is checked against the rows, every quote against the document, and it never writes Cypher.

## The consistency ceiling

Larkspur's answer key comes from the same spec as its graph, so these rows show the rules and the queries agree with the spec, not that Moot predicts anything.

| question | Moot | baseline | source |
|---|---|---|---|
| Larkspur: stale or retired decisions an agent was allowed to act on (of 20) | **0** | BM25 + change cues 4 · trust the ADR 20 | [gate eval](../eval/results_gate.md) |
| Larkspur, 90 questions (still holds? why? since when?): dead decisions called HOLDS (of 22) | **0** | RAG + same model 13 · RAG over stated reasons 7 | [head-to-head](../eval/results_baseline.md) |

<p align="center"><img src="charts/s3_verdicts.svg" alt="Study S3, verdicts right of 90: Moot 90, Moot rows narrated 89, depth 1 88, RAG over stated reasons 76, BM25 RAG 62, dates ignored 62, FalkorDB removed 60, trust the ADR 56" width="760"></p>

On the same 90 questions Moot gets 90/90 verdicts and 24/24 "since when" dates exactly; plain RAG with the same local model gets 62/90 and 8/24. The ablations say what carries it: ignoring dates drops Moot to 62/90, removing FalkorDB (same rules over retrieved documents) to 60/90, depth 1 to 88/90. Larkspur's labels share a spec with its graph, so Moot's row is a ceiling, not extraction quality ([threats](../eval/results_baseline.md#threats-to-validity-worst-first)).

<p align="center"><img src="charts/s3_dead_called_holds.svg" alt="Dead decisions called HOLDS of 22: Moot 0, depth 1 2, RAG over stated reasons 7, FalkorDB removed 8, BM25 RAG 13, trust the ADR 22" width="760"></p>

Every number above is checked by `moot verify` against the JSON the evals wrote (`moot verify --rerun` re-derives it from committed inputs), and the charts are drawn from the same files by `eval/charts.py` (verify fails if a committed chart drifts). Studies are registered before they run, withdrawn results stay listed with the reason ([docs/studies.md](studies.md)), and every table is in [docs/evaluation.md](evaluation.md).
