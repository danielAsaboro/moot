# Moot evaluation: every study in full

The README carries the headline numbers; this page carries every table behind them, the backtest on real repositories and the real-world ADR audit. Every number here is checked by `moot verify` against the JSON the evals wrote, and `moot verify --rerun` first re-runs the deterministic evals from committed inputs. Study registrations (written before each ran) and withdrawn results are in [studies.md](studies.md).

## Backtest: does it work on real history?

Every other result in this README is graded against an answer key we wrote, or has none. This one is graded by strangers. `make backtest` reads the git history of the ADR folders of **30 public repositories** (GOV.UK, Ministry of Justice, Open edX, Mozilla FxA, Backstage, Home Assistant, Kyma and others), and takes the maintainers' own commits as the answer key: a decision dies on the day its repository marked it superseded, deprecated or invalidated, archived it, or wrote a later ADR dropping the tool it picked. Then it rewinds each repository month by month, gives Moot only the evidence that existed that month (the tool's own commit history and dated license changes), and asks the agent gate the same question an agent would: may I act on this? The key never enters the graph, and was fixed before the gate ran. Full results, every death and every flag: [eval/results_backtest.md](../eval/results_backtest.md).

**Coverage, the finding that matters most.** 722 real decisions were in force at some point; 23 were later abandoned by their own repository. Only 97 (13%) pick an outside tool, and only **6 of the 23 deaths** are among them. Outside evidence can speak to about a quarter of the decisions real teams abandon. The rest die for internal reasons: a reorganisation, a project winding down, a developer preferring something else. Only a company's own documents can catch those, which is the case for the company graph in the README.

| on the 97 tool decisions (6,013 decision-months) | caught before maintainers | missed | flagged while still listed in force |
|---|---|---|---|
| **Moot gate** | **2 / 6** (recall 0.33, bootstrap 95% CI 0.00–0.80, Wilson 0.10–0.70) | 4 | 22 |
| trust the ADR | 0 / 6 | 6 | 0 |
| age ≥ 3 years | 3 / 6 | 3 | 73 |
| random, same number of flags | 1.4 / 6 | 4.6 | 22.6 |

Six deaths is too few to rank anything on recall, and we say so. Moot's two catches were license changes: GOV.UK combined its Mongo clusters in 2017, MongoDB went SSPL in October 2018, and GOV.UK replaced Mongo with DocumentDB a year later; Moot said DENY 350 days before the repository did. Its four misses were three internal decisions and one outside fact it does not read (Meta stopped recommending Create React App while CRA's repository still had commits). The 22 flags on decisions still listed as in force cannot be graded by the key, so we read each one: **15** rest on a premise that really died upstream and nobody revisited (Terraform's BSL, Lunr with no commit since 2020, Kubeless archived), **4** were later abandoned in another document without retiring the ADR (FxA moved from Intern to Playwright; MoJ moved from Elasticsearch to OpenSearch), **1** is mixed, and **2** are false alarms (a managed AWS Redis is not bound by Redis's license). The age rule raises 73 flags with no reason attached; every Moot flag names a dated fact a reviewer can check in a minute.

`make backtest` re-runs everything from GitHub (about 1.5 GB of blob-less clones). `make backtest-score` re-scores the committed snapshot in `data/backtest/` offline. The live checker's vulnerability premise is left out of the backtest: OSV dates an advisory, but not which release a team was on at a past date.

## Evaluation

Every study is listed in [docs/studies.md](studies.md) with its hypothesis written before it ran, and results we have withdrawn stay there, marked, with the reason. `moot verify` checks every number in this section against the JSON the evals wrote (`moot verify --rerun` first re-runs them from committed inputs) and exits non-zero on any mismatch.

`make eval` reproduces [eval/results.md](../eval/results.md) with no model: for the 16 decisions that have an invalidating document, does the method surface it?

| method | recall@5 of invalidating docs | decisions with ≥1 found |
|---|---|---|
| graph path query (Moot) | **1.00** (consistency check, see below) | **100%** |
| BM25 top-5, query = decision title + summary | 0.81 | 81% |
| random 5 docs (control) | 0.01 | – |

**The 1.00 is not a retrieval result.** The targets are the CONTRADICTS edges in `truth.json`, and the graph's CONTRADICTS edges are built from the same spec, so the graph reads back its own edges. It says the ingest kept them all. The BM25 row is the real finding: the document that kills a decision's reason is often unreachable by similarity to the decision.

`make eval-scale` reproduces [eval/results_scale.md](../eval/results_scale.md), also with no model. It pads the corpus with up to 20,000 extra documents about the same systems, seeds a graph for each size, and measures FalkorDB latency; then it scores verdicts against the ground truth and against a retrieval-only staleness heuristic. Warm numbers are nearest-rank p50 / p95 over n calls after warmup; *cold* is the first call on a freshly seeded graph, reported apart. Raw samples are in `eval/results_scale.json`.

| extra noise docs | audit warm n · p50 / p95 | audit cold | full ledger warm n · p50 / p95 | seed |
|---|---|---|---|---|
| 0 | 80 · 1.0 / 1.1 ms | 2.8 ms | 20 · 2.8 / 2.9 ms | 0.0 s |
| 1,000 | 80 · 0.9 / 1.1 ms | 2.4 ms | 20 · 2.7 / 3.1 ms | 0.0 s |
| 5,000 | 80 · 0.9 / 1.1 ms | 3.2 ms | 20 · 2.8 / 3.0 ms | 0.2 s |
| 20,000 | 80 · 0.9 / 1.1 ms | 4.5 ms | 20 · 2.9 / 3.0 ms | 0.6 s |

| verdicts (30 decisions) | exact | stale precision | stale recall | F1 |
|---|---|---|---|---|
| graph path rule (Moot) | **30/30** | **1.00** | **1.00** | **1.00** |
| BM25 top-5 + change-cue heuristic | – | 0.50 | 0.75 | 0.60 |

The audit is an index lookup plus a bounded path expansion, so its latency does not move with corpus size. These are laptop numbers measured with other work running, good for the shape of the curve, not for a production quote. The seed column is where FalkorDB taught us something: the first import matched edge endpoints without labels, which cannot use the per-label index and took three minutes at 20k documents; naming the labels on both ends brought it to under a second on an M-series Mac. The 30/30 shares the common-mode caveat above: the verdict rule and the ingest agree.

`make eval-gate` reproduces [eval/results_gate.md](../eval/results_gate.md), no model: would each method let an agent act on a decision it should not? An agent should act only on the 10 decisions that HOLD; the other 20 should be stopped.

| method | false allows (of 20) | 95% upper bound on the false-allow rate | of which stale (of 16) | false blocks (of 10) |
|---|---|---|---|---|
| Moot gate (full-depth audit + `gate()`) | **0** | 0.12 | **0** | 6, all REVALIDATE |
| BM25 top-5 + change-cue heuristic | 4 | 0.38 | 4 | 8 |
| trust the ADR (a doc-chat brain that finds it and stops) | 20 | 1.00 | 16 | 0 |

Zero false allows in 20 is a small sample: the one-sided 95% Wilson bound still allows a true rate up to 12%. The six false blocks are decisions the spec calls HOLDS whose reasons nobody ever checked: one premise below each has no evidence either way. The gate asks to revalidate them instead of allowing, and an owner's ruling settles each with a dated edge. Until 2026-10-18 the gate allowed them and printed "all premises hold"; that result is withdrawn ([docs/studies.md](studies.md#withdrawn-results)).

On the 25 real public ADRs, which have no answer key, the gate denies 7 (5 rest on a reason a GitHub or OSV check contradicts, 2 were retired by their own repository) and asks to revalidate 7 whose vulnerability check could not be answered; 23 of the 25 still say *accepted*. The same answer key built the graph, so the Larkspur zeros show the gate and verdict rules agree, not that extraction is solved.

`python3 eval/eval_ablation.py` reproduces [eval/results_ablation.md](../eval/results_ablation.md), pre-registered before its first run: does the graph carry the gate's answer, or would the rule text decide it anyway? It deletes random edges, and also adds random junk contradictions (the direction a deletion-only control cannot see), 20 seeds per level.

| arm | at 0% | at 100% (or 2× junk) |
|---|---|---|
| delete every CONTRADICTS edge: false allows, legacy rule (no evidence = holds) | 0 of 20 | 12 of 20 |
| delete every CONTRADICTS edge: false allows, current gate | 0 of 20 | 2 of 20 |
| add 28 random CONTRADICTS edges: holds decisions denied | 0 of 10 | 5.65 of 10 |

Deleting the evidence that killed a decision makes the legacy rule wave it through; the current gate turns the missing evidence into REVALIDATE instead. Junk contradictions get followed too: the gate cannot tell a plausible wrong edge from a real one, which is why every DENY names the evidence id for a human to check. One of the four predictions failed (deleting reason edges never raised false allows, because every stale Larkspur decision states exactly one premise), and the file says so.

`make eval-e2e` (needs a key) runs the model-in-the-loop comparison: a BM25 RAG company brain asked "does this still hold?" against Moot's graph verdict. The headline column is how many of the 16 decisions whose premise was contradicted each system still calls HOLDS, i.e. treats the dead premise as current; it also scores verdict accuracy and whether the cited document is the true invalidating one. Results land in `eval/results_e2e.md`.

## Real-world proof: public ADRs

Larkspur is invented. To show the engine works on real text, Moot also audits **25 real architecture decision records from 5 public GitHub repositories** ([ministryofjustice/cloud-platform](https://github.com/ministryofjustice/cloud-platform), [alphagov/govuk-infrastructure](https://github.com/alphagov/govuk-infrastructure), [alphagov/govuk-aws](https://github.com/alphagov/govuk-aws), [backstage/backstage](https://github.com/backstage/backstage), [thomvaill/log4brains](https://github.com/thomvaill/log4brains)), each of which picks a named open-source tool. It lives in its own named graph, `public_adrs`, next to the demo tenant; the verdicts come from the same path queries.

We read 144 ADRs from those repositories first. Most of their stated reasons are internal ("Jenkins took a week a month to keep alive") and cannot be checked from outside. What every tool choice does rest on, without saying so, is that the tool stays maintained, stays open source and stays free of known vulnerabilities. Those are the premises Moot checks, each as a dated `Evidence` node:

| check | source | contradicts the premise when |
|---|---|---|
| maintained | GitHub API | the repository is archived, or its default branch has no commit in the last 365 days |
| open source | GitHub license, then the LICENSE text | the only licenses offered are source-available (BUSL, SSPL, Elastic, RSAL) |
| no known vulnerability | [OSV.dev](https://osv.dev) | an advisory affects the tool's latest published version |

Snapshot of 2026-10-17 (`data/realworld/checks.json`, reproduced by `make realworld`): 26 tools, **71 checks answered, 6 failed, 7 could not be answered** and are listed as unchecked instead of guessed (three tools have no package in an OSV ecosystem; for four Go projects the module proxy's "latest" did not match the project's own latest release, so the vulnerability check refuses to answer). An unanswered check is still a `Premise` node, marked `unchecked` and carrying no evidence: the verdict does not move, but the audit reports it as unchecked rather than holding, and the agent gate says REVALIDATE. Every record's quote is verified against the ADR fetched from GitHub; a record whose quote is missing is dropped.

Two records have since been retired by their own repositories, and the graph says so with a dated `RETIRES` edge whose quote is verified against the retiring file: Backstage ADR013 (node-fetch) was superseded by ADR014 on 2024-11-29, and GOV.UK ADR 0007 (Fluent Bit and Elasticsearch) was marked "Deprecated (no superseding ADR)" on 2025-07-21. From those dates both are RETIRED, so node-fetch's failing maintenance check no longer counts against a decision that is not in force. Before them, time travel shows them as they were.

The five records that are still in force and rest on a reason that no longer holds (MOOT):

| ADR | decided | unwritten reason that no longer holds |
|---|---|---|
| log4brains: Use Lunr for search | 2020-11-03 | Lunr.js is maintained: last commit 2020-08-19 |
| GOV.UK AWS: Puppet architecture | 2017-07-04 | Puppet is maintained: last commit to puppetlabs/puppet main 2024-12-11 |
| GOV.UK: Prometheus Adapter for HPA metrics | 2025-06-03 | Prometheus Adapter is maintained: last commit 2025-04-01, two months before the ADR |
| GOV.UK: Use Crossplane | 2025-10-20 | latest Crossplane (v2.4.2) has no known vulnerability: 1 OSV advisory |
| MoJ: Use Kubernetes | 2018-04-10 | latest Kubernetes (v1.37.1) has no known vulnerability: 2 unfixed OSV advisories on `k8s.io/kubernetes` |

The licence checks all held: Elasticsearch and Redis both moved to source-available licences, and both now also offer AGPL, so "open source" still holds for them. Concourse CI was chosen by the Ministry of Justice in 2018 and by GOV.UK in 2025; in the graph that is one premise carrying two organisations' decisions. Limits: "no commit in a year" is a proxy for maintenance, not a verdict on quality; OSV advisories on the Kubernetes monorepo module include issues that are mitigated by configuration rather than fixed; and this is 25 records, not a survey.

## Head-to-head against a retrieval company brain (study S3)

Registered before it ran ([studies.md](studies.md#s3-head-to-head-graph-verdicts-against-a-retrieval-company-brain-with-ablations)): 90 frozen questions, each of Larkspur's 30 decisions on three dates, asked *does it still hold, which documents show it, since when?* The model arms share one local model (`qwen3.8:27b`), one prompt (which includes the verdict definitions) and one decoding; only the context differs. Full file: [eval/results_baseline.md](../eval/results_baseline.md).

| arm | verdicts right (of 90) | dead decisions called HOLDS (of 22) | cited a document that killed it (of 22) | "since when" exact (of 24) | false alarms on HOLDS (of 50) |
|---|---|---|---|---|---|
| **Moot** (graph verdict, depth 4) | **90** | **0** | **22** | **24** | 0 |
| Moot rows + model (the graph's path, narrated) | 89 | 0 | 22 | 18 | 0 |
| RAG: BM25 top-5 + model | 62 | 13 | 9 | 8 | 1 |
| RAG over stated reasons + model (FalkorDB removed) | 76 | 7 | 16 | 12 | 0 |
| ablation: depth 1 | 88 | 2 | 20 | 22 | 0 |
| ablation: no as_of (dates ignored) | 62 | 0 | 22 | 23 | 20 |
| ablation: FalkorDB removed, rules kept | 60 | 8 | 10 | 10 | 16 |
| trust the ADR | 56 | 22 | 0 | 0 | 0 |

What each prediction did: (1) Moot 90/90, the common-mode ceiling, as predicted. (2) Plain RAG called 13 of 22 dead decisions HOLDS and got 8 of 24 dates exactly, as predicted (at least 4; under half). (3) RAG over the stated reasons cited a killing document more often than plain RAG (16 vs 9) but still missed D01, whose dead reason is two hops down; D02 and D03 state the gateway limit directly, so it caught them. The prediction named all three: partly wrong. (4) Depth 1 called D01 HOLDS after PR-412, but not D02 and D03, for the same reason; it also missed D19. Partly wrong. (5) Ignoring dates got every past question whose answer differs from today's wrong and never answered NOT_YET, as predicted. (6) The model reading Moot's rows got 89/90, within 5, as predicted; its "since when" fell to 18/24 because the rows carry dates but not the verdict history, which `verdict_history` computes.

## EnterpriseRAG-Bench: a blind supersession graph

A separate study, run on someone else's benchmark: can a graph built *blind* (without reading the answer key) keep superseded documents out of a RAG context? Measured honestly, mostly no: Moot's frozen blind rules remove the superseded gold document in 1 of the 14 conflicts where BM25 leaks it (13/20 vs BM25's 14/20). A competing entry's oracle setup reaches 1/20 only because its graph was seeded from an inventory written by reading the gold answers. Full tables, the freeze manifest and the post-hoc arms: [eval/results_erag.md](../eval/results_erag.md).
