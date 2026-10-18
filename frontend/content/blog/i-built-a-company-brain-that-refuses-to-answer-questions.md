# I built a company brain that refuses to answer questions

*Moot, my entry for Graph Hacks (WeMakeDevs × FalkorDB), Company Brain track.*

Everyone at Graph Hacks is building a brain you can chat with. I built one that won't chat. Ask Moot "why do we cap uploads at 10 MB?" and it doesn't explain the rule to you. It tells you the rule is dead, what killed it, on which day, and which other rules died with it.

This post covers why I think that's the more useful question, how a graph answers it where search can't, and the parts of my own results I had to take back.

## The rule nobody could justify

Every team older than a year follows rules nobody can justify. The demo company in Moot, a fictional 30-person startup called Larkspur, has one that every engineer has met in some form:

> **D01: Cap file uploads at 10 MB.** All uploads pass through the API gateway, and the gateway enforces a 10 MB body limit.

That was true when Ada wrote it. Then in March, PR-412 raised the gateway's body limit to 100 MB for a different reason. Nobody went back to the upload rule. In May, Ada left. The rule is still enforced, the product still rejects an 11 MB file, and the only person who knew why is gone.

The decision outlived its reason. That's the problem Moot exists for.

## Why doc-chat can't see it

My first instinct was the obvious one: put the ADRs in a vector store and ask. That gives you a perfectly fluent wrong answer. The retriever finds D01, reads "because the gateway enforces a 10 MB limit", and repeats it back as fact.

The document that killed the reason is PR-412. It says "raise the gateway body limit to 100 MB". It never mentions uploads, and it has nothing to do with D01 on the surface. Similarity search finds documents *about the decision*. To audit a decision you need documents *about its reason*, and about the reason that reason depends on.

In Moot's eval, a BM25 search over the decision's title and summary surfaces the invalidating document for 81% of the stale decisions. That sounds decent until you remember the other 19% are exactly the cases nobody will ever catch by reading.

So reasons have to be nodes.

## The graph model in five lines

```
(Decision)-[:BECAUSE_OF]->(Premise)
(Premise)-[:DERIVED_FROM]->(Premise)
(Evidence)-[:SUPPORTS {at}]->(Premise)
(Evidence)-[:CONTRADICTS {at}]->(Premise)
(Person)-[:OWNS {valid_from, valid_to}]->(Decision)
```

A decision rests on premises. A premise can depend on another premise ("uploads go through the gateway" only matters while "the gateway caps bodies at 10 MB" is true). Every document that supports or contradicts a premise is an edge with a date on it. Ownership has a validity window, so "who owned this when it went stale" is a query too.

Nothing about validity lives in prose. That's the whole design.

## The verdict is a Cypher query, not an opinion

Here is the query that decides whether a decision still holds. It's the heart of Moot, and it runs on FalkorDB:

```cypher
MATCH (d:Decision {id: $id})
MATCH p = (d)-[:BECAUSE_OF|DERIVED_FROM*1..4]->(pr:Premise)
OPTIONAL MATCH (e)-[r:SUPPORTS|CONTRADICTS]->(pr)
  WHERE r.at <= $as_of
RETURN pr, nodes(p) AS pn, length(p) AS hops, collect({id: e.id, rel: type(r), at: r.at})
ORDER BY hops
```

A small pure-Python rule reads the rows: a premise whose latest event is a contradiction is expired; a decision with an expired premise within reach is MOOT. That's it.

Two things fall out of this for free.

**Depth.** At depth 1, D01 HOLDS, because its direct premise ("uploads go through the gateway") is still true. That's what a doc-chat brain sees. At depth 2 the path reaches the gateway limit, PR-412 contradicts it, and the verdict flips to MOOT. In the UI there's a depth toggle, and watching the verdict change as you slide it is the best ten seconds of the demo.

**Time travel.** `$as_of` is a parameter. Ask the same question as of June 2025 and you get HOLDS, because PR-412 doesn't exist yet. Run the whole ledger at every month end and you get a chart of decision rot: Larkspur went from 0 to 12 MOOT decisions in 22 months, and nobody changed a single ADR.

Every read goes through FalkorDB's `GRAPH.RO_QUERY`, which the engine itself refuses to run a write through. The model never writes Cypher. It gets rows, writes prose, and a validator throws the prose away if it cites any id the rows didn't contain.

## What the graph lets you ask that a table can't

Once reasons are nodes, other questions become one query each:

- **What did this PR just break?** `algo.SPpaths` from a new document to every decision it can reach. Trace PR-412 and it reaches D01 and the two other decisions that rest on the same gateway limit.
- **What if we no longer need SOC 2?** Pretend one premise broke today and show every decision that would fall, with the chain.
- **Who owns this now that Ada left?** Walk `REPORTS_TO` using only the edges that were valid *on the day she left*, and skip managers who also left. Lena reported to Ada; both are gone, so Lena's decisions climb to Kwame.
- **Which reasons are riskiest?** Rank premises by how many standing decisions sit below them. I tried PageRank first. It ranked the SOC 2 rotation premise 10th where a plain dependency count put it 3rd, because evidence edges pour score into whichever premises are most *discussed*, not most *depended on*. The count is the question a leader actually asks, and it explains itself, so that's what ships. PageRank stays in the API for comparison.

## The agent gate, and the bug I'm glad I found

Company brains are going to be read by agents, not only people. So Moot has a gate: before an agent enforces, relies on or renews a decision, it calls `check_action` (an MCP tool, or `GET /api/gate/D01`) and gets ALLOW, DENY or REVALIDATE with the path behind it.

The first version allowed 10 of Larkspur's decisions and printed "all premises hold". Then I looked at what "hold" meant. Six of those ten rested on a premise that had **no evidence at all**. Nothing contradicted it, but nothing had ever checked it either. My rule treated silence as support.

No evidence is not "holds". The fixed gate allows 4, still lets through zero of the 20 decisions it should stop, and asks an owner to revalidate the other 6. An owner's ruling is itself a dated edge, so the next audit reads it like any other evidence, and newer evidence reopens the question.

That cost me six "false blocks" in the eval table. I kept them. I'd rather an agent ask than act on a reason nobody ever checked. The old number is still in the repo, marked withdrawn, with the reason.

## Does it work on real history?

Larkspur is invented, and I wrote its answer key, so its 30/30 verdict score mostly shows that my ingest and my rule agree. I wanted something graded by strangers.

So I built a backtest. It reads the git history of the ADR folders of 30 public repositories (GOV.UK, Ministry of Justice, Open edX, Mozilla, Backstage, Home Assistant and others) and takes the maintainers' own commits as the answer key: a decision dies on the day its repo marked it superseded or deprecated. Then it rewinds each repo month by month, gives Moot only the evidence that existed that month, and asks the gate.

The headline isn't a recall number. It's a coverage number. Of 722 real decisions, 23 were later abandoned. Only 6 of those 23 had picked an outside tool, so only 6 could even in principle be caught by outside evidence like a license change or an archived repo. **Three in four real decisions die for internal reasons**: a reorg, a project winding down, someone preferring something else. Only a company's own documents can catch those. That's the strongest argument I found for building the company graph at all.

On the 6 it could see, Moot caught 2, both license changes. GOV.UK's MongoDB decision got a DENY 350 days before the repository replaced Mongo. Six is far too few to rank anything on, and the README says so in the first line of that table.

## Learnings, including the ones that hurt

**1. My best-looking number wasn't a result.** Retrieval recall of the invalidating document: graph 1.00, BM25 0.81, random 0.01. It looked great. But the graph's CONTRADICTS edges and the eval's targets came from the same spec, so the graph was reading back its own edges. It's a consistency check, and the README now says that right next to the number.

**2. I tried to beat a competitor's benchmark blind, and didn't.** Another team, Canon, reported a big gain on EnterpriseRAG-Bench's conflicting-information questions with a supersession graph. Reading their repo, I found their graph had been seeded from an inventory written by reading each question's gold answer. So I built the same idea blind: Moot could only read the question and the documents BM25 retrieved, and a test fails if the blind code ever names an answer-key field.

The result, counting questions where the superseded document is still in the model's context (lower is better): BM25 14 of 20, my frozen blind rules 13, the best post-hoc LLM extraction (qwen3.8 27B, run locally) 12, Canon's oracle setup 1. The bottleneck wasn't retrieval: in all 14 leaks, the current document was also in the top 10. It was extraction. Most conflicts are phrased as tiers, names or procedures, not "changed from X to Y". I report 13 as the headline because it was frozen before it ran; the 12 is labelled post-hoc everywhere.

I also found that in Canon's own published files, all 20 "info not found" answers were byte-identical across their arms, and the judge still scored them 13, 13 and 15. A single judged run can't separate a two-question effect from that noise.

**3. Write the hypothesis down before you run it.** After reading another entry's repo I added `docs/studies.md`: each study's prediction, committed before the script exists, and the result ships whatever it is. My graph ablation predicted four things; one failed, and the file says which.

**4. Make your README numbers checkable.** `moot verify` compares every number in the README against the JSON the evals wrote and exits non-zero on drift. `--rerun` re-derives them from committed inputs first, so a stale number in the README fails the build before a judge finds it.

**5. FalkorDB taught me to label both ends.** The first seed matched edge endpoints without labels, which can't use the per-label index. At 20,000 documents it took three minutes. Naming the labels on both ends brought it under a second. Audits stayed around a millisecond from 0 to 20,000 noise documents, because they're an index lookup plus a bounded path expansion.

## Honest limits

The demo corpus is synthetic. A premise can expire without anyone writing it down, and Moot only knows what was written. Extraction misses reasons that are implied rather than stated, and the ablation shows the gate follows a plausible wrong edge as faithfully as a right one, which is why every DENY names the evidence id for a human to check.

## What I'd do with another week

Live connectors for Slack, Linear and GitHub so premises are extracted as they're written; a scheduled re-audit that drafts the re-open memo itself; and an extraction agreement study on a real company's ADRs, which is where the real risk lives.

The one idea I'd keep if I threw everything else away: **a decision is only as alive as the dated evidence behind its reasons, and the graph, not the model, should decide.**

*Repo: github.com/danielAsaboro/moot · Built with Claude Code as a pair programmer; the graph model, verdict rules and studies were mine, and every result in this post is reproducible from the repo.*
