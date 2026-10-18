# Results, in full

Every study was registered in [studies.md](studies.md) before it ran. The README keeps the headline; this page keeps every number, and `moot verify` checks them all.

## K1 and K2: questions about Kubernetes as an organisation

K1 asks what Kubernetes' own records say: which KEP replaced this one and when, who led its SIG on a date, whether it was in force on a date, and whether its authors still lead a SIG. The gold is read from raw git history by a separate parser (`moot/k1.py`); the questions were frozen and hashed before any arm ran ([register](studies.md)). Same model, prompt and step budget for every model arm.

| arm (qwen3.8:27b, temperature 0) | test: exact match (95% CI) | dev | tokens (test) | $ at Groq's price (test) | median s per question (test) | tool calls (test) |
|---|---|---|---|---|---|---|
| **agent with Moot's graph tools** | **26/34** (0.60–0.88) | 11/12 | 131,474 | 0.042 | 11.0 | 74 |
| agent with file and git tools over the same checkouts | 22/34 (0.48–0.79) | 7/12 | 362,173 | 0.115 | 38.3 | 193 |
| BM25 RAG over the checkouts | 15/34 (0.29–0.61) | 7/12 | 84,837 | 0.026 | 28.4 | 0 |
| BM25 RAG over the checkouts and their history (post hoc) | 17/34 (0.34–0.66) | 7/12 | 67,031 | 0.020 | 22.8 | 0 |
| one fixed graph query per question, no model | 25/34 (0.57–0.85) | 10/12 | 0 | 0.000 | – | 0 |

- **Accuracy:** level with the file and git agent (only the graph agent right on 8 questions, only the file agent on 4, exact McNemar p = 0.39); ahead of BM25 RAG beyond chance (13 against 2, p = 0.007; against RAG over history 11 against 2, p = 0.022).
- **Fair baselines:** before any test answer was scored, three harness faults were fixed on dev and every affected arm re-run in full (the file agent could not reach `sigs.yaml` history or read past 6,000 characters; bare answers were dropped by the parser, which left RAG at 0); one name normaliser for every arm. Each is in the [register](studies.md); earlier answers are kept, not scored.
- **Post hoc, a product fix:** SIG leadership is now dated to the `sigs.yaml` commit instead of the quarter (registered before K2); on the rebuilt graph the same fixed query answers 26 of 34, median under a millisecond. The frozen row above stays 25.
- **Shared source:** Moot's graph is built from the same repositories the gold is read from, so the fixed-query row measures how faithfully the graph holds that history. The contest is between agents with different tools. [Full tables](../eval/results_k1.md).

### K2, the confirmation

K2 was registered before any of its questions existed and frozen before any arm ran: 78 questions over SIG Auth, Node, Network and Storage KEPs, K1's four kinds plus how many of a SIG's KEPs were in force on a date and whether a person led the owning SIG the day a KEP was created; the same model, harness and prompts as K1's final run, nothing tuned on its dev split.

| K2 arm (qwen3.8:27b, temperature 0) | test: exact match (95% CI) | dev | tokens (test) | $ at Groq's price (test) | median s per question (test) | tool calls (test) |
|---|---|---|---|---|---|---|
| **graph-tool agent** | **41/57** (0.59–0.82) | 13/21 | 189,181 | 0.060 | 10.9 | 117 |
| file and git agent over the same checkouts | 22/57 (0.27–0.52) | 12/21 | 723,781 | 0.229 | 40.5 | 271 |
| BM25 RAG at HEAD | 26/57 (0.33–0.58) | 10/21 | 131,478 | 0.040 | 25.8 | 0 |
| BM25 RAG over history (post hoc) | 27/57 (0.35–0.60) | 10/21 | 84,654 | 0.026 | 16.6 | 0 |
| fixed graph query, no model | 38/57 (0.54–0.78) | 14/21 | 0 | 0.000 | <0.001 | 0 |

- **Accuracy:** the graph agent is ahead of the file and git agent beyond chance (only the graph agent right on 22 questions, only the file agent on 3, exact McNemar p < 0.001) and of BM25 RAG (18 against 3, p = 0.001).
- **What the agent adds over the fixed query:** the fixed query answers 38 of 57 with no model; the graph agent answers those same 38 and 3 more, and none fewer. The 3 are all leaders of a KEP's SIG on a date before the KEP itself existed, where the graph's team edge for the KEP starts on its creation date and the fixed query finds no team: KEP-1435 (asked for 2019-07-26, created 2020-01-03), KEP-1669 (2019-05-25, created 2020-04-07) and KEP-4205 (2020-10-28, created 2023-05-25). The agent read the owning SIG and asked for its leaders on the day.
- **Against the registered prediction:** the margin over the file agent is at least K1's dev margin, as predicted, and largest where a date has to be joined to a person: whether someone led the owning SIG the day a KEP was created (11 of 11 against 1 of 11), and whether a KEP's authors lead a SIG today (11 against 6). Two parts did not hold: on how many of a SIG's KEPs were in force on a date every arm, the fixed query included, got 0 of 11 (the graph dates a KEP's force from its first implementable commit, the gold reads every status change), and RAG did not stay near zero (26 of 57). [Full tables](../eval/results_k2.md).

## Checks and supporting numbers

| what | result | note |
|---|---|---|
| Router: ordinary questions the keyword rules misroute, routed right by a tool call (of 22) | **20** | keyword rules 0 (chosen because they fail) · [router eval](../eval/results_router.md) |
| Oracle: the verdict FalkorDB's path query returns equals a plain-Python walk over the same edges | 2,000 of 2,000 random worlds | a check, not a win (`tests/test_oracle.py`) |
| NetworkX cross-check | WCC, betweenness ranking, PageRank's top premises and SPpaths lengths agree | betweenness scores differ, the order does not (`tests/test_algorithms.py`) |
| Unlearning (U1): remembered answers revoked when their evidence changes | over 12,792 monthly gate questions, so 0 stale answers are served, against 62 for a 90-day cache and 285 for a one-year cache | [U1](../eval/results_unlearn.md) |
| Audit latency at 20,000 noise documents, p50 | **0.9 ms** | flat from 0 to 20,000 · [scale eval](../eval/results_scale.md) |
| Larkspur: stale or retired decisions an agent was allowed to act on (of 20) | **0** | BM25 + change cues 4 · trust the ADR 20 · [gate eval](../eval/results_gate.md); a consistency ceiling: synthetic, graded by its own spec |
| Larkspur, 90 questions (still holds? why? since when?): dead decisions called HOLDS (of 22) | **0** | RAG + same model 13 · RAG over stated reasons 7 · [head-to-head](../eval/results_baseline.md); a consistency ceiling |

## Forecasting which decisions die

Calling each decision dead or alive (H1, H2, A1, P1, the backtest) is a game a constant answer wins, because deaths are rare. H3 was registered to ask the usable version, ranking decisions by risk (AUC, precision in the top 10%), on 447 repositories no earlier study used; only 29 of their tool decisions were in force on 2022-10-17 and none died by 2025-10-17, so by its own rule H3 is underpowered and makes no claim ([results_h3.md](../eval/results_h3.md)). Every number of the other studies follows.


Every study was registered in [docs/studies.md](studies.md) before it ran, and the results ship whatever they are. The short version: **on independent real data, Moot does not predict which decisions die better than the baselines.** Its value is the graph, the provenance and the gate in front of agents, not a forecast.

| question | Moot | baselines | source |
|---|---|---|---|
| **Held-out (H1):** 64 real decisions in force on 2023-10-17, graded by what their repositories did by 2026-10-17 (5 died): right | 52/64 (0.81) | everything HOLDS 59/64 · BM25 RAG 57/64 · LLM agent with GitHub/OSV tools 55/64 (64 of 64 answered) · age rule 28/64 · Moot rules without FalkorDB 24/64 | [results_heldout.md](../eval/results_heldout.md) |
| H1: deaths caught, false alarms | 1 of 5, 8 of 59 | BM25 RAG 2 and 4 · age rule 3 and 34 · LLM agent 1 and 5 | [results_heldout.md](../eval/results_heldout.md) |
| **Agents on real decisions (A1):** later-dead decisions an agent was allowed to act on / decisions that held but were blocked | 0 of 5 / 59 of 59 | trust the ADR 5 / 0 · BM25 RAG 3 / 4 · LLM agent 4 / 5 · age rule 2 / 34 | [results_heldout.md](../eval/results_heldout.md#what-an-agent-would-have-been-allowed-to-do-study-a1-test-split) |
| A1 with the product gate policy (post hoc): later-dead allowed / held blocked | 4 of 5 / 8 of 59 | as above | [results_heldout.md](../eval/results_heldout.md) |
| **Fresh held-out (H2):** 22 decisions from 16 other repositories, 2022-10-17 to 2025-10-17; only 1 died, so it is underpowered | 21/22 right, 0 of 1 caught | everything HOLDS 21/22 · age rule 14/22, 1 of 1 caught · LLM agent with GitHub/OSV tools 13/16 on the test split, 0 of 1 caught | [results_h2.md](../eval/results_h2.md) |
| **Precision on real history (P1):** flags later confirmed by the repository within three years | 1 of 12 (0.08) | age rule 3 of 45 (0.07) · random flagger 0.13 | [results_precision.md](../eval/results_precision.md) |
| Real repositories: decisions caught dead before their own maintainers (of 6 tool deaths) | **2** | age ≥ 3 years 3 · random 1.4 · trust the ADR 0 | [backtest, 30 public repos](../eval/results_backtest.md) |
| Real repositories: flags on decisions still listed in force, each with a dated reason | **22** (15 real, 2 false alarms) | age ≥ 3 years 73, none with a reason | [backtest](../eval/results_backtest.md#every-flag-on-a-decision-its-repository-still-lists-as-in-force) |
| EnterpriseRAG-Bench conflicts: superseded document still in the model's context (of 20, lower is better) | **13** | BM25 14: a tie | [blind supersession cut](../eval/results_erag.md) |
| Real public ADRs denied with a dated reason (of 25) | **7** | 23 of the 25 still say *accepted* | [real-world audit](evaluation.md#real-world-proof-public-adrs) |
| Router: ordinary questions the keyword rules misroute, routed right by a tool call (of 22) | **20** | keyword rules 0 (chosen because they fail) | [router eval](../eval/results_router.md) |
| Audit latency at 20,000 noise documents, p50 | **0.9 ms** | flat from 0 to 20,000 | [scale eval](../eval/results_scale.md) |

**Read it plainly.** On H1 calling everything HOLDS beats Moot's gate (59 against 52, exact McNemar p = 0.04), as the registration predicted: most of Moot's 8 false alarms are licence changes (Terraform, Nomad, Elasticsearch) that teams lived with. Applying the rule Moot already uses for ingested repositories, licence hits are DISPUTED unless a stated reason depends on them, gives 56/64 as a post-hoc row and catches none of the 5 deaths. In A1 the gate lets no later-dead decision through, but only because it blocks everything: with no dated evidence either way it says REVALIDATE, and that costs 59 of 59 decisions that held. What it adds is who to ask. On precision Moot is at chance. The backtest is where its flags read best: each names a dated reason a reviewer can check in a minute.

**On real history.** Rewound month by month with only the evidence of the day, Moot said DENY 350 days before GOV.UK replaced MongoDB (the SSPL licence change, October 2018), and 1,435 days before GOV.UK deprecated its Elasticsearch logging ADR; median lead 892 days. It found 15 ADRs still marked accepted whose reasons died upstream (the Terraform and Consul licence change, Lunr.js and sqlx gone quiet) and that nobody has revisited. ([backtest](../eval/results_backtest.md))

On recall the backtest cannot rank anything: the age rule catches 3 of the 6 deaths to Moot's 2, and six is too few to separate them. The difference is precision. To catch its 3, the age rule raises 73 flags on decisions still in force and says nothing about why; Moot raises 22, each naming a dated fact (a licence change, a repository gone quiet) that a reviewer can check in a minute, and reading all 22 found 15 whose reason really died upstream and 2 false alarms. On EnterpriseRAG-Bench, built blind, Moot's supersession cut ties BM25.

## Limits, in full

- **X1's judge is the local answer model**, running HERB's own prompts (the paper used gpt-4o); its PR-link extraction misses links HERB's own gold contains, so X1 also reports a registered deterministic row for People, Customer and Artifact.

- **Not a forecaster.** On held-out real decisions Moot does worse than calling everything HOLDS (52 against 59 of 64), and its flags on real history are confirmed at chance (1 of 12). It gives the reason, the path, the date and who to ask, not a prediction.
- **The gate trades one error for another.** The strict policy blocked all 59 held-out decisions that held; the product policy ("warn") lets them through with a warning and who to ask, and so also lets through 4 of the 5 that later died.
- **Larkspur is synthetic**, graded by its own spec: its zeros are a consistency ceiling. The backtest (722 real decisions, labelled by their maintainers) is graded by strangers; its six tool deaths are too few to rank recall.
- **Only what was written down.** Three in four abandoned real decisions picked no outside tool, so no outside check could see them die.
- **The gate follows the edges it is given**, junk included, which is why every DENY names the evidence id.
- **No evidence is not "holds"**: an unchecked reason is shown as unverified.
- **A stated reason is what the ADR says, not what is true.** The span check stops invented quotes, not a wrong reading of a real one; one local model, one run, no labelled set to score extraction.
- **Knowing is read from authorship**: KEP authors and approvers, git authors elsewhere. SIG leadership is dated to the `sigs.yaml` commit (K1 was frozen against quarter dating; its deterministic row is scored on that graph).
- **The Kubernetes graph covers four SIGs' KEPs** (every SIG's leadership), not the whole project; later KEPs rarely speak to earlier reasons, so most KEPs hold for want of contradiction, and the pass that reads them for SUPPORTS/CONTRADICTS edges is still running.
- The full-text resolver is keyword-based: a question with no word in common with a decision returns "unknown entity".
