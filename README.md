# Moot

**A company brain that finds the decisions your team still follows for reasons that no longer exist, and shows the evidence path.**

[![CI](https://github.com/danielAsaboro/moot/actions/workflows/ci.yml/badge.svg)](https://github.com/danielAsaboro/moot/actions/workflows/ci.yml)
[![Live app](https://img.shields.io/badge/live-moot.bringaihome.xyz-b5372b)](https://moot.bringaihome.xyz)
[![FalkorDB](https://img.shields.io/badge/FalkorDB-Cloud%20v4.22-1d1d1b)](docs/falkordb.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-5e5d58)](LICENSE)

| | |
|---|---|
| **Try it** | [Live app](https://moot.bringaihome.xyz) · [D01's evidence path](https://moot.bringaihome.xyz/app/?d=D01&tab=graph) · [the Cypher it ran](https://moot.bringaihome.xyz/app/?d=D01&tab=cypher) · [People](https://moot.bringaihome.xyz/app/people/) · [a real repo, audited](https://moot.bringaihome.xyz/app/ledger/?graph=gh_thomvaill_log4brains): log4brains, whose later ADR contradicts its Lerna decision |
| **Watch / read** | [Demo video](https://vimeo.com/1237038749) · [Blog: I built a company brain that refuses to answer questions](https://moot.bringaihome.xyz/i-built-a-company-brain-that-refuses-to-answer-questions/) |
| **Check it** | [Evaluation](docs/evaluation.md) · [Study S3 head-to-head](eval/results_baseline.md) · [Stated reasons, before/after](eval/results_reasons.md) · [Studies register](docs/studies.md) |
| **Build on it** | [Query catalogue](docs/queries.md) · [How FalkorDB is used](docs/falkordb.md) · [MCP setup](docs/mcp.md) · [Run it](#run-it) |

Built for [Graph Hacks](https://www.wemakedevs.org/hackathons/falkordb) (WeMakeDevs x FalkorDB), track **Company Brain**. [How it maps to the six judging criteria](#judging-criteria-where-to-look).

![Moot demo: ask why uploads are capped, flip depth 1 to 4, ask something not in the graph](docs/hero.gif)

## The story in 40 seconds

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

## Results

**On real history.** Rewound month by month with only the evidence of the day, Moot said DENY 350 days before GOV.UK replaced MongoDB (the SSPL licence change, October 2018), and 1,435 days before GOV.UK deprecated its Elasticsearch logging ADR; median lead 892 days. It found 15 ADRs still marked accepted whose reasons died upstream (the Terraform and Consul licence change, Lunr.js and sqlx gone quiet) and that nobody has revisited. ([backtest](eval/results_backtest.md))

| question | Moot | baseline | source |
|---|---|---|---|
| Larkspur: stale or retired decisions an agent was allowed to act on (of 20) | **0** | BM25 + change cues 4 · trust the ADR 20 | [gate eval](eval/results_gate.md) |
| Larkspur, 90 questions (still holds? why? since when?): dead decisions called HOLDS (of 22) | **0** | RAG + same model 13 · RAG over stated reasons 7 | [head-to-head](eval/results_baseline.md) |
| Real repositories: decisions caught dead before their own maintainers (of 6 tool deaths) | **2** | age ≥ 3 years 3 · random 1.4 · trust the ADR 0 | [backtest, 30 public repos](eval/results_backtest.md) |
| Real repositories: flags on decisions still listed in force, each with a dated reason | **22** (15 real, 2 false alarms) | age ≥ 3 years 73, none with a reason | [backtest](eval/results_backtest.md#every-flag-on-a-decision-its-repository-still-lists-as-in-force) |
| EnterpriseRAG-Bench conflicts: superseded document still in the model's context (of 20, lower is better) | **13** | BM25 14: a tie | [blind supersession cut](eval/results_erag.md) |
| Real public ADRs denied with a dated reason (of 25) | **7** | 23 of the 25 still say *accepted* | [real-world audit](docs/evaluation.md#real-world-proof-public-adrs) |
| Audit latency at 20,000 noise documents, p50 | **0.9 ms** | flat from 0 to 20,000 | [scale eval](eval/results_scale.md) |

<p align="center"><img src="docs/charts/s3_verdicts.svg" alt="Study S3, verdicts right of 90: Moot 90, Moot rows narrated 89, depth 1 88, RAG over stated reasons 76, BM25 RAG 62, dates ignored 62, FalkorDB removed 60, trust the ADR 56" width="760"></p>

On the same 90 questions Moot gets 90/90 verdicts and 24/24 "since when" dates exactly; plain RAG with the same local model gets 62/90 and 8/24. The ablations say what carries it: ignoring dates drops Moot to 62/90, removing FalkorDB (same rules over retrieved documents) to 60/90, depth 1 to 88/90. Larkspur's labels share a spec with its graph, so Moot's row is a ceiling, not extraction quality ([threats](eval/results_baseline.md#threats-to-validity-worst-first)).

<p align="center"><img src="docs/charts/s3_dead_called_holds.svg" alt="Dead decisions called HOLDS of 22: Moot 0, depth 1 2, RAG over stated reasons 7, FalkorDB removed 8, BM25 RAG 13, trust the ADR 22" width="760"></p>

On recall the backtest cannot rank anything: the age rule catches 3 of the 6 deaths to Moot's 2, and six is too few to separate them. The difference is precision. To catch its 3, the age rule raises 73 flags on decisions still in force and says nothing about why; Moot raises 22, each naming a dated fact (a licence change, a repository gone quiet) that a reviewer can check in a minute, and reading all 22 found 15 whose reason really died upstream and 2 false alarms. On EnterpriseRAG-Bench, built blind, Moot's supersession cut ties BM25.

Every number above is checked by `moot verify` against the JSON the evals wrote (`moot verify --rerun` re-derives it from committed inputs), and the charts are drawn from the same files by `eval/charts.py` (verify fails if a committed chart drifts). Studies are registered before they run, withdrawn results stay listed with the reason ([docs/studies.md](docs/studies.md)), and every table is in [docs/evaluation.md](docs/evaluation.md).

## Real repositories: reading the reasons an ADR states

Real ADRs rarely name a tool in their title, so the first version of the GitHub connector left most of them UNDOCUMENTED: it had nothing it could check. Now a model reads each ADR's Context, Decision and Consequences and proposes the reasons it states; a validator keeps a reason only if its quote is a literal span of the ADR (outside the title and Status line), and stores the span, section, document and model on the `Premise`. A reason that depends on a catalogued tool is linked (`DERIVED_FROM`) to that tool's GitHub and OSV checks, and each later ADR is judged against earlier reasons, with exact quotes, as dated `SUPPORTS` / `CONTRADICTS` evidence. Replies are cached in `data/github/<repo>/reasons.json`, so CI and the live site never call a model.

<p align="center"><img src="docs/charts/reasons_before_after.svg" alt="Verdicts per ingested repository before and after reading stated reasons" width="760"></p>

On the four ingested repositories, UNDOCUMENTED fell from 46 to 18 of 75 decisions. Of the 35 HOLDS after, 2 pass the gate; the rest say why but nobody has evidence either way, so the gate answers REVALIDATE, not ALLOW. The reading also found 5 new MOOT decisions, each through a dated contradiction a human can check: 4 from the maintenance check on a tool a stated reason depends on (Puppet, last commit to main 2024-12-11) and 1 from a later ADR's own words (log4brains: Lerna "does not integrate well with Git Flow processes"). Licence and vulnerability hits are advisory here: Terraform's move to BUSL-1.1 or an OSV advisory on Kubernetes makes a decision DISPUTED, so its owner rules, and it can make one MOOT only through a reason the ADR states that depends on it. None of the 31 tool-linked reasons does, so 8 decisions that an earlier version called MOOT on those checks alone (GOV.UK's EKS choices among them) are DISPUTED now. And the gate got stricter, not looser: ALLOW went from 8 to 2, because five decisions that passed on their title's tool checks now also rest on a reason their ADR states and nobody has checked. 157 reasons kept from 75 ADRs, 6 dropped by the validator; 18 decisions are still UNDOCUMENTED. Full table, what the validator dropped, and every verdict that changed: [eval/results_reasons.md](eval/results_reasons.md).

## Screens

| | |
|---|---|
| ![The evidence path for D01: the decision, its stated reason, the expired reason two hops down, and PR-412 contradicting it](docs/screens/evidence-path.png) **Evidence path.** Every verdict is drawn from the rows FalkorDB returned: D01, the reason, the expired reason behind it, PR-412. | ![The Cypher tab: the exact parameterised queries the answer ran, with rows and milliseconds](docs/screens/cypher.png) **Cypher.** The exact read-only queries each answer ran, with parameters, row counts and milliseconds. |
| ![People: decisions only one person here can explain, bus factor, knowledge islands from algo.WCC, bridges from betweenness](docs/screens/people.png) **People.** Who only knows what: bus factor, `algo.WCC` knowledge islands and betweenness on a KNOWS projection. | ![The Graph picker: Larkspur, 25 public ADRs, the backtest and each ingested GitHub repository](docs/screens/graph-picker.png) **Graph picker.** One named graph per company: Larkspur, real ADRs, the backtest, every ingested repository. |
| ![log4brains: a stated reason, its exact quote from the ADR, and the later ADR that contradicts it](docs/screens/stated-reason.png) **Stated reasons.** log4brains chose Lerna because "Yarn + Lerna seems to be a very good practice"; its own later ADR says Lerna "does not integrate well". The exact words, the source and the model that read them. | ![The landing page](docs/screens/landing.png) **Landing.** Straight links to the evidence path, the Cypher, People and an audited repository. |

## Judging criteria: where to look

| criterion | the evidence |
|---|---|
| **Graph-native use of FalkorDB** | Verdicts *are* path queries: `(Decision)-[:BECAUSE_OF\|DERIVED_FROM*1..depth]->(Premise)<-[:SUPPORTS\|CONTRADICTS]-(Evidence)` with dated edges, all through `GRAPH.RO_QUERY` ([queries](docs/queries.md)). `algo.WCC`, `algo.betweenness`, `algo.pageRank` and `algo.SPpaths` answer who knows why, what leaves with a person, blast radius and what a PR broke. One named graph per company; Findings, rulings and handovers are written back only after approval ([docs/falkordb.md](docs/falkordb.md)). Removing FalkorDB but keeping the rules drops S3 from 90/90 to 60/90. |
| **Agent effectiveness** | The agent gate (`check_action`, `GET /api/gate`) let 0 of 20 stale or retired Larkspur decisions through, against 4 for BM25 with change cues and 20 for trusting the ADR ([gate eval](eval/results_gate.md)). On real history it caught 2 of 6 tool deaths before the maintainers did ([backtest](eval/results_backtest.md)). Same local model, graph context vs retrieval: 90/90 vs 62/90 ([S3](eval/results_baseline.md)). |
| **Potential impact** | Every team inherits rules whose reasons died quietly. Moot works on any public GitHub repository today (`moot ingest-github owner/repo`): four are in the live app, with stated reasons read from their ADR text ([before/after](eval/results_reasons.md)), and 25 real public ADRs are checked against GitHub and OSV. |
| **Technical excellence** | One-command setup (`docker compose up --build`, or `make demo`), 145 tests, CI on FalkorDB v4.22.1 and v4.18.3 plus the UI build, `moot verify --rerun` re-derives every README number from committed inputs. Deployed at [moot.bringaihome.xyz](https://moot.bringaihome.xyz) on FalkorDB Cloud. |
| **Explainability and provenance** | Every answer carries its traversal path, the evidence ids and dates, the Cypher it ran, and a digest of the rows it read. A model's citation is checked against the rows; a stated reason's quote against the document, with its character span, section, source link and model on the node. "No evidence" is never "holds". |
| **Creativity and presentation** | A brain that refuses: it says MOOT, REVALIDATE or "not in the graph" instead of an answer. Isometric drawings of the real rows, an unplugged cable for an expired reason, the ruled ledger, the [video](https://vimeo.com/1237038749) and the [blog](https://moot.bringaihome.xyz/i-built-a-company-brain-that-refuses-to-answer-questions/). |

## Submission checklist

- [x] FalkorDB is the primary database and the product stops working without it: every verdict is a `ro_query` path query
- [x] Data: a synthetic 8-person company (Larkspur: 30 decisions, 238 documents: 30 ADRs and 208 PRs, tickets, chat and docs), 25 real public ADRs checked against GitHub and OSV, a backtest on 722 real decisions from 30 public repositories, and a connector for any public GitHub repository (four ingested: 75 decisions, 59 pull requests, 157 stated reasons)
- [x] Graph data model, key Cypher queries and graph algorithms ([below](#graph-model), [full catalogue](docs/queries.md))
- [x] Setup in one command ([Run it](#run-it)), MCP server ([setup](docs/mcp.md))
- [x] Demo video: https://vimeo.com/1237038749
- [x] Live deployment: https://moot.bringaihome.xyz (FalkorDB Cloud)
- [x] AI use disclosed ([below](#ai-disclosure))

## Architecture

```mermaid
flowchart LR
  subgraph Sources
    C[Larkspur corpus<br/>ADRs, PRs, tickets, chat, docs]
    CK[GitHub + OSV checks]
    GH[any GitHub repo<br/>ADR folder, git history, PRs]
  end
  GH -->|moot ingest-github| RS[reasons.py<br/>model proposes stated reasons;<br/>quote must be a literal span;<br/>cached in reasons.json]
  RS --> J
  C -->|extract: quotes must be substrings| J[graph.json]
  CK -->|dated Evidence| J
  J -->|MERGE, idempotent| F[(FalkorDB<br/>one named graph per company)]
  F -->|GRAPH.RO_QUERY<br/>fixed parameterised Cypher| T[tools.py]
  T --> V[verdict.py<br/>pure rules: verdict + agent gate]
  T --> PE[people.py<br/>KNOWS projection in a scratch graph:<br/>algo.WCC, algo.betweenness]
  V --> A[agent.py<br/>narrate, validate citations]
  A --> API[FastAPI + Next.js UI]
  A --> MCP[MCP server]
  A --> CLI[moot CLI]
  API -->|Approve click only| W[Finding / OWNS / ruling writes]
  W --> F
```

The four outcomes the organisers' reference architecture asks for: `answered_with_path`, `answered_from_memory`, `not_in_graph`, `unknown_entity`. Nothing is written to the graph without an approval call.

How a stated reason gets into the graph:

```mermaid
sequenceDiagram
  participant ADR as ADR text (git)
  participant M as model (local qwen3.8:27b)
  participant V as validator
  participant G as graph.json → FalkorDB
  ADR->>M: Context, Decision, Consequences + tools named
  M-->>V: reasons [{text, quote, tool}]
  V->>V: quote is a literal span? outside title/Status? tool named in the quote?
  V-->>G: Premise {text, quote, span, section, source, extracted_by} ←BECAUSE_OF─ Decision
  V-->>G: Premise ─DERIVED_FROM→ tool premises (GitHub / OSV checks)
  ADR->>M: each later ADR + earlier reasons sharing its words
  M-->>V: relations [{reason_id, rel, quote}]
  V-->>G: Evidence(later ADR) ─SUPPORTS/CONTRADICTS {at: its date, quote}→ Premise
```

## Graph model

One named graph per company (`select_graph(tenant)`): `larkspur` (demo), `public_adrs` (real ADRs), `backtest` (30 real repositories), and one `gh_<owner>_<repo>` graph per repository brought in with `moot ingest-github`. All of them are selectable in the UI (the Graph menu), the API (`?graph=`) and the MCP audit, gate, ledger and people tools (`graph=`).

```mermaid
graph LR
  D[Decision] -->|BECAUSE_OF| P[Premise]
  P -->|DERIVED_FROM| P2[Premise]
  E[Evidence] -->|CONTRADICTS at| P2
  E2[Evidence] -->|SUPPORTS at| P
  D -->|RECORDED_IN| E3[Evidence: the ADR]
  Per[Person] -->|OWNS valid_from..valid_to| D
  Per -->|AUTHORED| E
  Per -->|REPORTS_TO valid_from..valid_to| M[Person]
  D -->|GOVERNS| S[System]
  D2[Decision] -->|SUPERSEDES at| D
  F[Finding] -->|ABOUT| D
  F -->|CITES| E
```

| Label | Key properties | Meaning |
|---|---|---|
| `Decision` | id, title, summary, decided_on, source | a standing decision (one per ADR) |
| `Premise` | id, text, kind (stated / unwritten), unchecked; for a stated reason: quote, span, section, source, extracted_by | a reason behind one or more decisions |
| `Evidence` | id, kind (adr / pr / ticket / chat / doc / check), title, date, excerpt | a dated document |
| `Person` | id, name, role, joined, left | people, with tenure |
| `System` | id, name | what a decision governs |
| `Finding` | id, verdict, kind (verdict / reopen / ruling), as_of, digest | Moot's own memory, written only after a human approves |

Every event edge (`SUPPORTS`, `CONTRADICTS`, `SUPERSEDES`, `RETIRES`) carries `at`, the date it took effect, and optionally `stated`, the date it became known; an edge a model proposed also carries the exact `quote` and `extracted_by`. Ownership and reporting lines carry validity windows. Indexes: a range index on `id` for every label, full-text on `Decision(title, summary)`, `Premise(text)` and `Evidence(title, excerpt)`. The full edge list is in [docs/queries.md](docs/queries.md).

## The queries and algorithms Moot depends on

The model never writes Cypher. These are the core of the fixed catalogue in `moot/tools.py`; the [full catalogue](docs/queries.md) has all of them.

**The audit**: premises up to `depth` hops, with every dated event known by `as_of`. This query is the verdict.

```cypher
MATCH (d:Decision {id: $id})
MATCH p = (d)-[:BECAUSE_OF|DERIVED_FROM*1..4]->(pr:Premise)
OPTIONAL MATCH (e)-[r:SUPPORTS|CONTRADICTS]->(pr)
  WHERE r.at <= $as_of AND coalesce(r.stated, r.at) <= $as_of
OPTIONAL MATCH (a:Person)-[:AUTHORED]->(e)
RETURN pr, nodes(p) AS pn, length(p) AS hops,
       collect({id: e.id, rel: type(r), at: r.at, quote: r.quote, author: a.name})
ORDER BY hops
```

Pure rules in `moot/verdict.py` then decide: a premise is **expired** when its latest event is a contradiction, **disputed** when contradicted then re-affirmed, **unevidenced** when nothing ever checked it. A decision is **RETIRED** if a dated `SUPERSEDES`/`RETIRES` points at it, **UNDOCUMENTED** with no premise, **MOOT** if any premise within `depth` hops is expired. The **agent gate** audits at depth 6 and answers **ALLOW**, **DENY** or **REVALIDATE** (no evidence is not "holds").

**Who knows why** a decision was made: everyone who owns it, wrote its ADR, or wrote evidence on any reason below it.

```cypher
MATCH (d:Decision {id: $id})
OPTIONAL MATCH (d)-[:BECAUSE_OF|DERIVED_FROM*1..6]->(pr:Premise)<-[:SUPPORTS|CONTRADICTS]-(e:Evidence)<-[:AUTHORED]-(p1:Person)
OPTIONAL MATCH (d)-[:RECORDED_IN]->(:Evidence)<-[:AUTHORED]-(p2:Person)
OPTIONAL MATCH (p3:Person)-[o:OWNS]->(d) WHERE o.valid_from <= $as_of
RETURN collect(DISTINCT p1.id) + collect(DISTINCT p2.id) + collect(DISTINCT p3.id)
```

**What leaves with them**: the who-knows-why rows are written into a scratch graph as `KNOWS` edges between each person still here and each decision they know; the person leaving is removed and `algo.WCC` finds the knowledge islands. An island with decisions and no person left in it is knowledge that walks out of the door. The company graph is never written, and the scratch graph is deleted before the answer returns. (We started with `GRAPH.COPY`; on macOS the embedded server's copy fork can deadlock, so the projection is built from rows.)

```cypher
CALL algo.WCC({nodeLabels: ['Person','Decision'], relationshipTypes: ['KNOWS','KNOWN_BY']}) YIELD node, componentId
RETURN componentId, collect(CASE WHEN node:Decision THEN node.id END), collect(CASE WHEN node:Person THEN node.id END)
```

**Bridges between people**: `algo.betweenness` on the same projection ranks the people through whom most knowledge runs. Its scores are not NetworkX's exact Brandes values on this projection, but the people come out in the same order, which is what Moot reports (`tests/test_algorithms.py` cross-checks WCC, betweenness ranks, PageRank's top premises and SPpaths lengths against NetworkX). **Single points of failure**: reasons that two or more live decisions rest on, vouched for by one document or one person still here.

**Blast radius of a reason**: every decision that rests on it, directly or through derived reasons, plus `algo.pageRank` over the dependency graph for comparison.

```cypher
MATCH (pr:Premise {id: $id})
MATCH p = (d:Decision)-[:BECAUSE_OF|DERIVED_FROM*1..6]->(pr)
RETURN DISTINCT d.id, d.title, length(p)
```

**What did this PR break?** `algo.SPpaths` from a new document to every decision it can reach.

```cypher
MATCH (e:Evidence {id: $id}), (d:Decision)
CALL algo.SPpaths({sourceNode: e, targetNode: d,
     relTypes: ['CONTRADICTS','SUPPORTS','BECAUSE_OF','DERIVED_FROM'], relDirection: 'both', maxLen: 6, pathCount: 1})
YIELD path RETURN d.id, length(path), nodes(path)
```

**Orphaned decisions**: walk `REPORTS_TO` as it stood the day the owner left, skipping managers who also left.

```cypher
MATCH path = (o:Person {id: $pid})-[:REPORTS_TO*1..5]->(m:Person)
WHERE all(r IN relationships(path) WHERE r.valid_from <= $left_on AND (r.valid_to = '' OR r.valid_to > $left_on))
  AND (m.left = '' OR m.left > $as_of)
RETURN m.id, m.name, length(path) ORDER BY length(path) LIMIT 1
```

Read-only is enforced by the engine: every read is `GRAPH.RO_QUERY`, which FalkorDB refuses to run a write through. The UI's **Cypher** tab shows the exact queries each answer ran, with row counts and milliseconds.

## Run it

One command, with Docker (FalkorDB + Moot, seeded on start):

```bash
docker compose up --build     # http://localhost:8000
```

Or locally without Docker (FalkorDB embedded through `falkordblite`, Node 20+ for the UI):

```bash
pip install -e ".[dev]" && make demo     # db + seed + ui + serve on http://localhost:8000
```

Then:

```bash
moot ask "why do we cap uploads" --depth 1 --as-of 2025-06-01
moot ledger                              # every decision with its verdict, MOOT first
moot departure marcus                    # what leaves with a person
moot people                              # who only knows what: bus factor and betweenness per person
moot ingest-github thomvaill/log4brains  # any public repo's ADRs, history and PRs into graph gh_thomvaill_log4brains, audited
moot packet D01                          # the evidence packet behind one verdict, as Markdown
moot verify                              # every number in this README checked against the eval JSON, charts included
moot mcp                                 # MCP server on stdio (Claude Desktop, Claude Code, Cursor)
make test                                # pytest; CI runs it and moot verify --rerun against FalkorDB v4.22 and v4.18
```

`ingest-github` reads stated reasons with a local model through [Ollama](https://ollama.com) (`qwen3.8:27b` by default; `MOOT_REASONS_BACKEND=groq` with a `GROQ_API_KEY` instead) and caches every reply; without a model it reads the cache and leaves unread ADRs UNDOCUMENTED. `python3 eval/eval_reasons.py --cached` rebuilds the before/after table, `python3 eval/charts.py` the charts, `node eval/screens.mjs` the screenshots.

**MCP**: `claude mcp add moot -- python3 -m moot.cli mcp`, or `{"mcpServers": {"moot": {"command": "python3", "args": ["-m", "moot.cli", "mcp"], "cwd": "/path/to/moot"}}}` for Claude Desktop and Cursor. The agent's first call is `check_action`; [docs/mcp.md](docs/mcp.md) lists every tool. `GROQ_API_KEY` in `.env` turns on the live model (`moot/llm.py`, `openai/gpt-oss-120b` by default, `ANTHROPIC_API_KEY` as the alternative): it picks the answer tool by tool call and narrates, under a daily spend cap (`MOOT_LLM_DAILY_USD`, default $1), and falls back to the keyword rules and templates when it is off, over the cap or wrong. On 22 ordinary questions the keyword rules misroute it routes 20 correctly ([router eval](eval/results_router.md)). Verdicts never need it.

## Honest limits

- **Larkspur is synthetic**, and its answer key comes from the same spec as its graph, so on Larkspur the zeros show the rules agree with the spec, not that extraction is solved. The backtest is the result graded by strangers: 722 real decisions, labelled by their own maintainers' status changes. Its six tool deaths are too few to rank anything on recall, and we say so.
- **Moot only knows what was written down.** Three in four real decisions that teams abandoned picked no outside tool, so no outside check could have seen them die. Only a company's own documents can.
- **The gate follows the edges it is given.** The ablation shows random junk contradictions are followed like real ones, which is why every DENY names the evidence id for a human to check.
- **No evidence is not "holds".** A reason nobody ever checked makes the gate say REVALIDATE, which costs six false blocks on Larkspur. We chose that over letting an agent act on an unchecked reason.
- **A stated reason is what the ADR says, not what is true.** Reading reasons from prose moves decisions from UNDOCUMENTED to HOLDS, but most of those reasons have no dated evidence either way, so the gate still says REVALIDATE. The span check stops invented quotes, not a wrong reading of a real one; every reason links to its sentence so a reader can check it. One local model, one run, no labelled set of real reasons to score extraction against.
- **The GitHub connector reads what repositories publish.** It parses status lines and "superseded by" links, picks tools by name from the ADR title or a quoted reason, and checks maintenance, licence and known vulnerabilities. A status change is dated by the last commit to the file, never earlier than the change.
- **Knowing is read from authorship.** A person who knows why but never wrote anything down does not count, and the public repositories' people are their git authors.
- The full-text resolver is keyword-based: a question that shares no words with a decision returns "unknown entity", by design.

## AI disclosure

Built with Claude (Claude Code) as a pair programmer under the author's direction: the graph model, verdict rules, query design and corpus spec were specified by the author; Claude wrote most of the code, the synthetic documents and this README from those specifications, and the author reviewed and tested every piece. Inside the product, a model narrates answers and proposes extractions: stated reasons in real ADRs are read by a local open-weights model (`qwen3.8:27b` through Ollama), and the S3 retrieval arms use the same model. It never decides a verdict, never writes Cypher and never touches the database; every quote it proposes is kept only if it is a literal span of the source. Rulings, findings and handovers are written by fixed queries after a human approves, never by the model.

## License

MIT.
