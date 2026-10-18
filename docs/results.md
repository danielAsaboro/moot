# Results, in full

The README keeps the headline and a compact table; this is every result, with the reading of each. `moot verify` checks every number here.


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
