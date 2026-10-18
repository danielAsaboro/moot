# I built a company brain that refuses to answer questions

*Moot, my entry for Graph Hacks (WeMakeDevs × FalkorDB), Company Brain track.*

Everyone at Graph Hacks is building a brain you can chat with. I built one that won't chat. Ask Moot "why do we cap uploads at 10 MB?" and it doesn't explain the rule to you. It tells you the rule is dead, what killed it, on which day, and which other rules died with it.

This post covers why I think that's the more useful question, how a graph answers it where search can't, and the parts of my own results I had to take back.

> **Since this post (2026-10-21).** Moot now reads the reasons a real ADR states in its own words (a model proposes, a validator keeps only exact quoted spans), which cut UNDOCUMENTED from 46 to 18 of 75 decisions in four real repositories. A head-to-head on 90 frozen Larkspur questions with the same local model scored Moot 90/90 against plain RAG's 62/90; since Larkspur's answer key shares a spec with its graph, that is a consistency ceiling, not a field result. Questions are now routed by a model's tool call (Groq, with a daily spend cap, falling back to the keyword rules), and the hosted app reuses one FalkorDB connection, so the slow first load is gone. The numbers below are as they were when the post went up; the README has the current ones.

## The rule nobody could justify

Every team older than a year follows rules nobody can justify. The demo company in Moot, a fictional 8-person startup called Larkspur, has one that every engineer has met in some form:

> **D01: Cap file uploads at 10 MB.** All uploads pass through the API gateway, and the gateway enforces a 10 MB body limit.

That was true when Ada wrote it. Then in March, PR-412 raised the gateway's body limit to 100 MB for a different reason. Nobody went back to the upload rule. In May, Ada left. The rule is still enforced, the product still rejects an 11 MB file, and the only person who knew why is gone.

The decision outlived its reason. That's the problem Moot exists for.

## Why doc-chat can't see it

My first instinct was the obvious one: put the ADRs in a vector store and ask. That gives you a perfectly fluent wrong answer. The retriever finds D01, reads "because the gateway enforces a 10 MB limit", and repeats it back as fact.

The document that killed the reason is PR-412. It says "raise the gateway body limit to 100 MB". It never mentions uploads, and it has nothing to do with D01 on the surface. Similarity search finds documents *about the decision*. To audit a decision you need documents *about its reason*, and about the reason that reason depends on.

In Moot's eval, a BM25 search over the decision's title and summary surfaces the invalidating document for 81% of the stale decisions. That sounds decent until you remember the other 19% are exactly the cases nobody will ever catch by reading.

So reasons have to be nodes.

![Asking Moot which decisions are moot: one read-only tool, five FalkorDB queries, and the rows come back as the answer](/blog/ask-moot.png)

## The graph: five kinds of node, every edge dated

::diagram schema | The Larkspur graph as it sits in FalkorDB right now, with live counts. Red and green are the only edges a verdict reads; the rest answer "who" and "what".

| Node | What it holds | In Larkspur |
|---|---|---|
| `Decision` | a standing rule, one per ADR: id, title, summary, `decided_on` | 30 |
| `Premise` | one reason, with a kind: fact, constraint, assumption or unwritten | 28 |
| `Evidence` | a dated document: ADR, PR, ticket, chat message or doc | 238 |
| `Person` | people, with `joined` and `left` | 8 |
| `System` | what a decision governs | 10 |
| `Finding` | Moot's own memory: an approved verdict, re-open memo or owner ruling | written on approval |

The part that matters fits in five lines:


```
(Decision)-[:BECAUSE_OF]->(Premise)
(Premise)-[:DERIVED_FROM]->(Premise)
(Evidence)-[:SUPPORTS {at}]->(Premise)
(Evidence)-[:CONTRADICTS {at}]->(Premise)
(Person)-[:OWNS {valid_from, valid_to}]->(Decision)
```

A decision rests on premises. A premise can depend on another premise ("uploads go through the gateway" only matters while "the gateway caps bodies at 10 MB" is true). Every document that supports or contradicts a premise is an edge with a date on it. Ownership has a validity window, so "who owned this when it went stale" is a query too.

Nothing about validity lives in prose. That's the whole design. Because `SUPPORTS` and `CONTRADICTS` carry an `at` (when the change took effect) and an optional `stated` (when someone wrote it down), the same graph answers the question for any day in its history without copying anything.

![D07 in Moot: the decision, its reason, and the pull request that contradicted it, drawn from the rows FalkorDB returned](/blog/decision-d07.png)

## The verdict is a Cypher query, not an opinion

A verdict takes three steps. Only the first touches the database, and no model is involved in any of them.

### Step 1: one path query

This is the query `audit_decision` sends, copied from `moot/tools.py` with the depth and the date filter filled in:

```cypher
MATCH (d:Decision {id: $id})
MATCH p = (d)-[:BECAUSE_OF|DERIVED_FROM*1..4]->(pr:Premise)
OPTIONAL MATCH (e)-[r:SUPPORTS|CONTRADICTS]->(pr)
  WHERE r.at <= $as_of AND coalesce(r.stated, r.at) <= $as_of
OPTIONAL MATCH (a:Person)-[:AUTHORED]->(e)
RETURN pr, nodes(p) AS pn, length(p) AS hops,
       collect({id: e.id, title: e.title, rel: type(r), at: r.at,
                stated: r.stated, quote: r.quote, author: a.name})
ORDER BY hops
```

It walks every premise within four hops of the decision, through premises that depend on other premises, and collects every dated piece of evidence for or against each one. The `stated` filter matters: a document written in June that says a limit changed in March didn't exist yet in April, so an audit run as of April must not see it.

### Step 2: each premise gets a state

The rows go into a pure function. This is the real one from `moot/verdict.py`, minus its docstring:

```python
def premise_state(events):
    if not events:
        return "unevidenced"
    ordered = sorted(events, key=event_order)    # by at, then stated
    rulings = [i for i, e in enumerate(ordered) if e.get("kind") == "ruling"]
    if rulings:
        ordered = ordered[rulings[-1]:]   # a ruling settles the past
    if ordered[-1]["rel"] == "CONTRADICTS":
        return "expired"
    if any(e["rel"] == "CONTRADICTS" for e in ordered):
        return "disputed"
    return "holds"
```

Four states, decided by the order of dated events and nothing else. On the same day, an affirmation sorts after a contradiction, and an owner's ruling sorts after both, because the person ruling had seen them.

### Step 3: the decision gets a verdict

::diagram verdict | `decision_verdict` in `moot/verdict.py`, checked top to bottom. One expired premise anywhere within reach is enough to make a decision moot.

Two things fall out of this for free.

### Depth

::diagram depth-flip | D01 as the graph returns it. At depth 1 the audit stops at a premise nothing contradicts. One more hop reaches the gateway limit that PR-412 killed.

At depth 1, D01 HOLDS: its direct premise ("uploads go through the gateway") has nothing against it. That's all a doc-chat brain sees. At depth 2 the path reaches the gateway limit, PR-412 contradicts it, and the verdict flips to MOOT. The UI has a depth toggle, and watching the verdict change as you slide it is the best ten seconds of the demo. Across the whole company, depth 1 finds 10 moot decisions and depth 2 finds 12: two rules are dead only because of a reason *behind* a reason.

### Time

::diagram rot | Every verdict in Larkspur at each month end, from `GET /api/timeline?depth=4`. The dashed line is the moot count a one-hop audit would report.

`$as_of` is a parameter. Ask about D01 as of June 2025 and you get HOLDS, because PR-412 doesn't exist yet. Run the whole ledger at every month end and you get the chart above: Larkspur went from 0 to 12 moot decisions in 22 months, peaking at 13 in July 2026 before one was re-affirmed, and nobody edited a single ADR.

Every read goes through FalkorDB's `GRAPH.RO_QUERY`, which the engine itself refuses to run a write through. The model never writes Cypher. It gets rows, writes prose, and a validator throws the prose away if it cites any id the rows didn't contain.

## What the graph lets you ask that a table can't

![The ledger on 18 Oct 2026: 12 moot, 4 disputed, 10 still valid, each verdict a path query](/blog/ledger.png)

Once reasons are nodes, other questions become one query each:

- **What did this PR just break?** `algo.SPpaths` from a new document to every decision it can reach. Trace PR-412 and it reaches D01 and the two other decisions that rest on the same gateway limit.
- **What if we no longer need SOC 2?** Pretend one premise broke today and show every decision that would fall, with the chain.
- **Who owns this now that Ada left?** Walk `REPORTS_TO` using only the edges that were valid *on the day she left*, and skip managers who also left. Lena reported to Ada; both are gone, so Lena's decisions climb to Kwame.
- **Which reasons are riskiest?** Rank premises by how many standing decisions sit below them. I tried PageRank first. It ranked the SOC 2 rotation premise 10th where a plain dependency count put it 3rd, because evidence edges pour score into whichever premises are most *discussed*, not most *depended on*. The count is the question a leader actually asks, and it explains itself, so that's what ships. PageRank stays in the API for comparison.

### What did PR-412 break?

`trace_document` asks FalkorDB for the shortest path from one document to every decision, through reasons, in either direction:

```cypher
MATCH (e:Evidence {id: $id}), (d:Decision)
CALL algo.SPpaths({sourceNode: e, targetNode: d,
  relTypes: ['CONTRADICTS','SUPPORTS','BECAUSE_OF','DERIVED_FROM'],
  relDirection: 'both', maxLen: 6, pathCount: 1}) YIELD path
RETURN d.id, d.title, length(path), nodes(path)
```

::diagram blast | One pull request about the gateway, three dead rules. D01 is the hardest to find: it's three hops away and its own premise never mentions a limit.

### Who inherits Ada's rules?

Ownership and reporting lines both carry validity windows, so the handover walk only uses edges that were true on the day the person left:

```cypher
MATCH (o:Person {id: $pid})
MATCH path = (o)-[:REPORTS_TO*1..5]->(m:Person)
WHERE all(r IN relationships(path)
          WHERE r.valid_from <= $left_on
            AND (r.valid_to = '' OR r.valid_to > $left_on))
  AND (m.left = '' OR m.left > $as_of)
RETURN m.id, m.name, length(path)
ORDER BY length(path) LIMIT 1
```

::diagram handover | Lena reported to Ada. Both have left, so the walk skips Ada and stops at the first manager still here.

### Which reasons are riskiest?

| Rank | Premise | Standing decisions on it | State | PageRank rank |
|---|---|---|---|---|
| 1 | Infra spend must stay under $20,000 a month | 3 of 4 | unevidenced | 1 |
| 2 | We need SOC 2 to sell to enterprises | 3 | unevidenced | 2 |
| 3 | The SOC 2 auditor requires rotation every 90 days | 2 | holds | **10** |
| 4 | We sell to customers in the EU | 1 of 2 | unevidenced | 3 |

The two riskiest reasons in the company have never been checked by any document. That's a better to-do list than any dashboard I've built.

## The agent gate, and the bug I'm glad I found

![Asking whether an agent can change the Friday deploy freeze: one read-only tool, seven queries, a DENY with the path D07 → p_no_rollback ← PR-350](/blog/ask-gate.png)

Company brains are going to be read by agents, not only people. So Moot has a gate: before an agent enforces, relies on or renews a decision, it calls `check_action` (an MCP tool, or `GET /api/gate/D01`) and gets ALLOW, DENY or REVALIDATE with the path behind it.

The first version allowed 10 of Larkspur's decisions and printed "all premises hold". Then I looked at what "hold" meant. Six of those ten rested on a premise that had **no evidence at all**. Nothing contradicted it, but nothing had ever checked it either. My rule treated silence as support.

No evidence is not "holds". The fixed gate allows 4, still lets through zero of the 20 decisions it should stop, and asks an owner to revalidate the other 6. An owner's ruling is itself a dated edge, so the next audit reads it like any other evidence, and newer evidence reopens the question.

::diagram gate | Every Larkspur decision through `check_action` today. Only four have dated support for every reason within six hops.

| The graph shows | Gate |
|---|---|
| not in the graph, not decided yet, retired, or any premise contradicted | **DENY** |
| no premise recorded, a premise disputed, never evidenced or uncheckable, owner has left, or no evidence in the whole graph | **REVALIDATE** |
| every premise has dated support, and none of the above | **ALLOW**, with that evidence as the basis |

| On 30 labelled decisions | false allows (of 20) | false blocks (of 10) |
|---|---|---|
| Moot gate | **0** | 6, all REVALIDATE |
| BM25 top-5 + change-cue heuristic | 4 | 8 |
| trust the ADR (what a doc-chat brain does) | 20 | 0 |

That cost me six "false blocks" in the eval table. I kept them. I'd rather an agent ask than act on a reason nobody ever checked. The old number is still in the repo, marked withdrawn, with the reason.

## Does it work on real history?

Larkspur is invented, and I wrote its answer key, so its 30/30 verdict score mostly shows that my ingest and my rule agree. I wanted something graded by strangers.

So I built a backtest. It reads the git history of the ADR folders of 30 public repositories (GOV.UK, Ministry of Justice, Open edX, Mozilla, Backstage, Home Assistant and others) and takes the maintainers' own commits as the answer key: a decision dies on the day its repo marked it superseded or deprecated. Then it rewinds each repo month by month, gives Moot only the evidence that existed that month, and asks the gate.

The headline isn't a recall number. It's a coverage number. Of 722 real decisions, 23 were later abandoned. Only 6 of those 23 had picked an outside tool, so only 6 could even in principle be caught by outside evidence like a license change or an archived repo. **Three in four real decisions die for internal reasons**: a reorg, a project winding down, someone preferring something else. Only a company's own documents can catch those. That's the strongest argument I found for building the company graph at all.

| On the 97 decisions that picked an outside tool | caught before the maintainers | flags on decisions still in force |
|---|---|---|
| **Moot gate** | **2 of 6** | 22 |
| age of 3 years or more | 3 of 6 | 73, none with a reason |
| random, same number of flags | 1.4 of 6 | 22.6 |
| trust the ADR | 0 of 6 | 0 |

On the 6 it could see, Moot caught 2, both license changes. GOV.UK's MongoDB decision got a DENY 350 days before the repository replaced Mongo. Six is far too few to rank anything on, and the README says so in the first line of that table. The 22 flags on decisions still marked in force are more interesting: I read every one. Fifteen rest on a premise that really died upstream and nobody revisited (Terraform's BSL change, Lunr with no commit since 2020, Kubeless archived), four were abandoned in another document without retiring the ADR, one is mixed, and two are false alarms.

## Learnings, including the ones that hurt

**1. My best-looking number wasn't a result.** Retrieval recall of the invalidating document: graph 1.00, BM25 0.81, random 0.01. It looked great. But the graph's CONTRADICTS edges and the eval's targets came from the same spec, so the graph was reading back its own edges. It's a consistency check, and the README now says that right next to the number.

**2. I tried a supersession graph on a public benchmark, blind, and it tied BM25.** EnterpriseRAG-Bench has 20 conflicting-information questions: an older and a newer document disagree, and a good brain should keep the superseded one out of the model's context. I built the graph blind: Moot could only read the question and the documents BM25 retrieved, and a test fails if the blind code ever names an answer-key field.

The result, counting questions where the superseded document is still in the model's context (lower is better): BM25 14 of 20, my frozen blind rules 13, the best post-hoc LLM extraction (qwen3.8 27B, run locally) 12. A tie, within noise. The bottleneck wasn't retrieval: in all 14 leaks, the current document was also in the top 10. It was extraction. Most conflicts are phrased as tiers, names or procedures, not "changed from X to Y". I report 13 as the headline because it was frozen before it ran; the 12 is labelled post-hoc everywhere.

**3. Write the hypothesis down before you run it.** I added `docs/studies.md`: each study's prediction, committed before the script exists, and the result ships whatever it is. My graph ablation predicted four things; one failed, and the file says which.

**4. Make your README numbers checkable.** `moot verify` compares every number in the README against the JSON the evals wrote and exits non-zero on drift. `--rerun` re-derives them from committed inputs first, so a stale number in the README fails the build before a judge finds it.

**5. FalkorDB taught me to label both ends.** The first seed matched edge endpoints without labels, which can't use the per-label index. At 20,000 documents it took three minutes. Naming the labels on both ends brought it under a second. Audits stayed around a millisecond from 0 to 20,000 noise documents, because they're an index lookup plus a bounded path expansion:

| Extra noise documents | One audit, p50 / p95 | Whole ledger, p50 | Seed |
|---|---|---|---|
| 0 | 1.0 / 1.1 ms | 2.8 ms | 0.0 s |
| 5,000 | 0.9 / 1.1 ms | 2.8 ms | 0.2 s |
| 20,000 | 0.9 / 1.1 ms | 2.9 ms | 0.6 s |

## Honest limits

The demo corpus is synthetic. A premise can expire without anyone writing it down, and Moot only knows what was written. Extraction misses reasons that are implied rather than stated, and the ablation shows the gate follows a plausible wrong edge as faithfully as a right one, which is why every DENY names the evidence id for a human to check.

## What I'd do with another week

Live connectors for Slack, Linear and GitHub so premises are extracted as they're written; a scheduled re-audit that drafts the re-open memo itself; and an extraction agreement study on a real company's ADRs, which is where the real risk lives.

The one idea I'd keep if I threw everything else away: **a decision is only as alive as the dated evidence behind its reasons, and the graph, not the model, should decide.**

*Repo: github.com/danielAsaboro/moot · Built with Claude Code as a pair programmer; the graph model, verdict rules and studies were mine, and every result in this post is reproducible from the repo.*
