# Moot

**Find the decisions your team still follows for reasons that no longer exist.**

Moot is a company brain that does not answer "what do we do?" It answers "which of our standing decisions still hold, which rest on a premise that has since stopped being true, and where is the evidence?" Decisions, their premises and dated evidence live in a FalkorDB graph. Verdicts are path queries. The model only narrates, and every citation it writes is checked against the rows.

Built for [Graph Hacks: Context for AI Agents](https://www.wemakedevs.org/hackathons/falkordb) (WeMakeDevs x FalkorDB, Oct 2026). Track: **Company Brain**.

![Moot demo: ask why uploads are capped, flip depth 1 to 4, ask something not in the graph](docs/hero.gif)

## Submission checklist

- [x] FalkorDB is the primary database and the product stops working without it: every verdict is a `ro_query` path query ([graph model](#graph-model), [queries](#the-queries-moot-depends-on))
- [x] Data is synthetic: a fictional 30-person company, Larkspur, with 30 decisions and 208 documents ([data/corpus](data/corpus))
- [x] README has setup steps and the graph data model
- [x] README lists the Cypher queries and graph algorithms the product depends on
- [ ] Demo video (link below when recorded)
- [ ] Live deployment (link below), full local setup is in [Run it](#run-it)
- [x] AI use disclosed ([below](#ai-disclosure))

## What a judge sees in 40 seconds

1. Ask **"Why do we cap uploads at 10 MB?"** Moot answers **MOOT**: the decision rests on "all uploads pass through the API gateway", which rests on "the gateway enforces a 10 MB body limit", which PR-412 contradicted on 2026-03-02 when the limit went to 100 MB. The owner, Ada, left in May. Two more decisions rest on the same dead premise.
2. Flip **depth 1 → 4**. At depth 1 the verdict is HOLDS, because the direct premise is intact. At depth 2 the chain reaches the dead premise. A doc-chat brain stops at depth 1.
3. Set **as of 2025-06-01**. The same question now answers HOLDS, because the contradicting PR does not exist yet.
4. Ask **"Why do we use Postgres for everything?"** → **UNDOCUMENTED**: the ADR states no premise, so there is nothing to check. Ask "why is the sky blue" → **not in the graph**.
5. Click **Approve: re-open** (or **Record this verdict** on a decision that holds). Only now does Moot write: a `Finding` node with the verdict, the date and the evidence it cites. Ask again and the outcome is *answered from memory*.
6. Look at the **Decision rot** chart: the ledger re-run at every month end. Larkspur went from 0 to 12 MOOT decisions in 22 months without anyone changing an ADR. Click a month to travel there.
7. Open the **Graph** tab for the path drawn from the rows, and the **Cypher** tab for the exact read-only queries FalkorDB ran for that answer, with row counts and milliseconds. That tab is the proof that the database, not the model, decided.
8. Click **Orphaned decisions**. Ada left in May and Lena left last week; four live decisions have no owner. Each one is routed up the reporting line *as it stood on the day the owner left*: Lena reported to Ada, who had already gone, so her decisions climb one more level to Kwame. The reasons and verdict travel with each decision. **Hand to Kwame** writes a new dated `OWNS` edge; the old one stays, so time travel still shows who owned it then.
9. Open a MOOT decision. Instead of a ticket, Moot drafts a **re-open memo**: which reason broke, the dated evidence that broke it, which other decisions rest on the same reason, and who should own the follow-up (the current owner, or the handover successor if they left). **Approve** writes a `Finding` with the memo, the cited evidence and an `ASSIGNED_TO` edge. Nothing happens before that click.
10. Ask **"What if we no longer need SOC 2?"** Moot pretends that reason broke today and shows the three decisions that would fall, HOLDS → MOOT, each with the chain from the decision through the premise that derives from it. **Riskiest reasons** ranks every reason by how many standing decisions sit below it; the $20k tooling budget carries three. Ask "what if churn goes above 5%?" and Moot says no reason in the graph mentions it.

## Run it

Local, no Docker (FalkorDB embedded via `falkordblite`):

```bash
git clone https://github.com/danielAsaboro/moot && cd moot
pip install -e ".[dev]"
make db        # starts FalkorDB on :6379 from the falkordblite package
make seed      # idempotent MERGE of data/graph.json into the "larkspur" graph
make serve     # http://localhost:8000
```

Docker (FalkorDB server + Moot):

```bash
docker compose up --build     # app on :8000, FalkorDB Browser on :3000
```

Optional: `ANTHROPIC_API_KEY` in `.env` turns on model narration, LLM extraction and the end-to-end eval. Verdicts never need it.

CLI:

```bash
moot ledger                              # every decision with its verdict, MOOT first
moot ask "why do we freeze deploys on fridays"
moot ask "why do we cap uploads" --depth 1 --as-of 2025-06-01
moot audit D01                           # the raw rows
moot mcp                                 # MCP server on stdio (Claude Desktop, Claude Code, Cursor)
```

MCP config for Claude Desktop or Claude Code:

```json
{"mcpServers": {"moot": {"command": "python3", "args": ["-m", "moot.cli", "mcp"], "cwd": "/path/to/moot"}}}
```

## Graph model

One named graph per company (`select_graph(tenant)`). Nodes:

| Label | Key properties | Meaning |
|---|---|---|
| `Decision` | id, title, summary, decided_on, source | a standing decision (one per ADR) |
| `Premise` | id, text, kind (fact / constraint / assumption) | a stated reason behind one or more decisions |
| `Evidence` | id, kind (adr / pr / ticket / chat / doc), title, date, excerpt | a dated document |
| `Person` | id, name, role, joined, left | people, with tenure |
| `System` | id, name | what a decision governs |
| `Finding` | id, verdict, kind (verdict / reopen), as_of, depth, created_at, note | Moot's own memory: an approved verdict or re-open memo |

Edges:

```
(Decision)-[:BECAUSE_OF {quote}]->(Premise)          the stated reason
(Premise)-[:DERIVED_FROM]->(Premise)                 a premise that only holds while another does
(Evidence)-[:SUPPORTS {at, quote}]->(Premise)        dated affirmation
(Evidence)-[:CONTRADICTS {at, quote}]->(Premise)     dated contradiction
(Decision)-[:RECORDED_IN]->(Evidence)                the ADR itself
(Person)-[:OWNS {valid_from, valid_to, handed_over_from}]->(Decision)  ownership with a validity window; a handover adds a newer edge
(Person)-[:REPORTS_TO {valid_from, valid_to}]->(Person)  the reporting line, dated
(Person)-[:AUTHORED]->(Evidence)
(Decision)-[:GOVERNS]->(System)
(Decision)-[:SUPERSEDES]->(Decision)
(Finding)-[:ABOUT]->(Decision), (Finding)-[:CITES]->(Evidence), (Finding)-[:SUPERSEDED_BY]->(Finding)
(Finding)-[:ASSIGNED_TO]->(Person)                   who owns the follow-up of a re-open memo
```

```mermaid
graph LR
  D[Decision] -->|BECAUSE_OF| P[Premise]
  P -->|DERIVED_FROM| P2[Premise]
  E[Evidence] -->|CONTRADICTS at| P2
  E2[Evidence] -->|SUPPORTS at| P
  Per[Person] -->|OWNS valid_from..valid_to| D
  Per -->|REPORTS_TO valid_from..valid_to| M[Person]
  D -->|GOVERNS| S[System]
  F[Finding] -->|ABOUT| D
  F -->|CITES| E
```

Indexes: range index on `id` for every label; full-text on `Decision(title, summary)`, `Premise(text)` and `Evidence(title, excerpt)` for entity resolution.

Verdict rules (pure Python in `moot/verdict.py`, applied to the rows the queries return):

- a premise is **expired** when its latest dated event (≤ as-of) is a CONTRADICTS; **disputed** when it was contradicted and later re-affirmed; **holds** otherwise
- a decision is **RETIRED** if another decision supersedes it; **UNDOCUMENTED** if it has no premise; **MOOT** if any premise within `depth` hops is expired; **DISPUTED** if any is disputed; **HOLDS** otherwise

## The queries Moot depends on

The model never writes Cypher. These parameterised queries are the whole tool catalogue (`moot/tools.py`), exposed to the agent, the API and the MCP server.

**1. Entity resolution** (full-text index; the question's content words, OR-ed, prefix-matched)

```cypher
CALL db.idx.fulltext.queryNodes('Decision', $q) YIELD node, score
RETURN node.id, node.title, node.summary, node.decided_on, score ORDER BY score DESC LIMIT $limit
```

**2. The audit**: premises up to `depth` hops, with every dated event on each premise. This is the verdict.

```cypher
MATCH (d:Decision {id: $id})
MATCH p = (d)-[:BECAUSE_OF|DERIVED_FROM*1..4]->(pr:Premise)
OPTIONAL MATCH (e:Evidence)-[r:SUPPORTS|CONTRADICTS]->(pr) WHERE r.at <= $as_of
RETURN pr, nodes(p) AS pn, length(p) AS hops,
       collect({id: e.id, title: e.title, kind: e.kind, rel: type(r), at: r.at, quote: r.quote})
ORDER BY hops
```

`nodes(p)` is returned with every answer and drawn in the UI as the path chain. `$as_of` makes the same question answer differently on different dates.

**3. Shared-premise impact** with PageRank over the whole dependency graph, so expired premises rank by what depends on them:

```cypher
MATCH (pr:Premise {id: $id})
MATCH p = (d:Decision)-[:BECAUSE_OF|DERIVED_FROM*1..6]->(pr)
OPTIONAL MATCH (d)-[:GOVERNS]->(s:System)
RETURN DISTINCT d.id, d.title, length(p), collect(DISTINCT s.name)
```
```cypher
CALL algo.pageRank(null, null) YIELD node, score WHERE node:Premise RETURN node.id, score
```

**4. Trace a new document** to every decision it can reach (`algo.SPpaths`): "what did this PR just break in our rulebook?"

```cypher
MATCH (e:Evidence {id: $id}), (d:Decision)
CALL algo.SPpaths({sourceNode: e, targetNode: d,
     relTypes: ['CONTRADICTS','SUPPORTS','BECAUSE_OF','DERIVED_FROM'], relDirection: 'both', maxLen: 6, pathCount: 1})
YIELD path RETURN d.id, d.title, length(path), nodes(path)
```

**5. Ownership as of a date** (validity windows on the edge; the latest edge that had started by `$as_of` wins, so a handover never erases history):

```cypher
MATCH (p:Person)-[o:OWNS]->(d:Decision) WHERE o.valid_from <= $as_of AND ($id IS NULL OR d.id = $id)
RETURN d.id, p.id, p.name, p.role, o.valid_from, o.valid_to, o.handed_over_from ORDER BY d.id, o.valid_from
```

**6. The ledger**, one pass for every decision:

```cypher
MATCH (d:Decision) OPTIONAL MATCH (n:Decision)-[:SUPERSEDES]->(d)
OPTIONAL MATCH p = (d)-[:BECAUSE_OF|DERIVED_FROM*1..4]->(pr:Premise)
OPTIONAL MATCH (e:Evidence)-[r:SUPPORTS|CONTRADICTS]->(pr) WHERE r.at <= $as_of
WITH d, n, pr, collect({rel: type(r), at: r.at}) AS ev
OPTIONAL MATCH (d)-[:GOVERNS]->(s:System)
RETURN d, n.id, pr.id, ev, collect(DISTINCT s.name) ORDER BY d.id
```

**7. Orphaned decisions → successor.** For every live decision whose owner of record has left, walk `REPORTS_TO` using the edges that were valid on the day the owner left, and stop at the first person who is still here. A manager who also left is skipped, not chosen.

```cypher
MATCH (o:Person {id: $pid}) MATCH path = (o)-[:REPORTS_TO*1..5]->(m:Person)
WHERE all(r IN relationships(path) WHERE r.valid_from <= $left_on AND (r.valid_to = '' OR r.valid_to > $left_on))
  AND (m.left = '' OR m.left > $as_of)
RETURN m.id, m.name, m.role, [n IN nodes(path) | {id: n.id, name: n.name, left: n.left}], length(path)
ORDER BY length(path) LIMIT 1
```

**8. The re-open memo** is assembled from queries 2, 3 and 7: the expired premise and its contradicting evidence (2), every other decision on the same premise (3), the suggested owner (5, then 7 if the owner left). The text is a template over those rows; the server rebuilds it on approval, so a client cannot record a memo the graph does not support.

**9. What if a reason broke today?** Every decision that rests on the premise, directly or through derived premises, with the chain. Any of them that is not already MOOT or RETIRED would flip to MOOT.

```cypher
MATCH (pr:Premise {id: $id})
MATCH p = (d:Decision)-[:BECAUSE_OF|DERIVED_FROM*1..4]->(pr)
RETURN d.id, d.title, nodes(p), length(p) ORDER BY length(p)
```

Free-text "what if" questions resolve to a premise with the `Premise(text)` full-text index; on a tie the broader reason (more decisions below it) wins. No match means "no reason in the graph mentions that".

**10. Riskiest reasons**: every premise with the decisions below it and its own dated events, ranked by how many *standing* (not yet MOOT, not RETIRED) decisions would fall with it.

```cypher
MATCH (pr:Premise) OPTIONAL MATCH (d:Decision)-[:BECAUSE_OF|DERIVED_FROM*1..4]->(pr)
OPTIONAL MATCH (e:Evidence)-[r:SUPPORTS|CONTRADICTS]->(pr) WHERE r.at <= $as_of
RETURN pr.id, pr.text, pr.kind, collect(DISTINCT d.id), collect(DISTINCT {rel: type(r), at: r.at})
```

We compared this count with `algo.pageRank` over the whole graph. PageRank ranks differently (the SOC 2 rotation premise is 3rd by count and 10th by PageRank) because evidence edges pour score into whichever premises are most discussed, not the ones most depended on. The count is the question a leader asks, and it explains itself, so the ranking uses the count; PageRank stays in the API (`pagerank_rank`) for comparison.

**The writes**, each behind an approval button. A handover is one `CREATE (p)-[:OWNS {valid_from: $as_of, valid_to: '', handed_over_from: $prev}]->(d)`. A verdict or re-open memo is a `Finding` that supersedes the previous finding for the decision and cites the evidence it relied on.

```cypher
MATCH (d:Decision {id: $did})
OPTIONAL MATCH (prev:Finding)-[:ABOUT]->(d) WHERE NOT (prev)-[:SUPERSEDED_BY]->()
WITH d, collect(prev) AS prevs
CREATE (f:Finding {id: $fid, verdict: $verdict, as_of: $as_of, depth: $depth, created_at: $now})-[:ABOUT]->(d)
...  (prev)-[:SUPERSEDED_BY]->(f), (f)-[:CITES]->(e)
```

Also used: `algo.WCC` in tests and exploration to cluster decisions that share premises, and `db.idx.fulltext.createNodeIndex` for the indexes above.

## Architecture

```
corpus (ADRs, PRs, tickets, chat, docs)
   │  moot extract  (model proposes; every quote must be a substring of its document, or it is dropped)
   ▼
truth.json / extracted.json ──► graph.json ──► moot seed (MERGE, idempotent) ──► FalkorDB, one graph per company
                                                                                   │
            ┌──────── read-only parameterised Cypher tools (ro_query) ─────────────┘
            ▼
   verdict.py (pure)  ──►  agent.py: resolve → audit → memory check → narrate → validate citations
            │                       │
      FastAPI + web UI        MCP server (stdio)      moot CLI
            │
   Approve ──► write_finding (verdict or re-open memo) · handover (new dated OWNS edge)
```

Four outcomes, as the organisers' reference architecture asks: `answered_with_path`, `answered_from_memory`, `not_in_graph`, `unknown_entity`.

## Evaluation

`make eval` reproduces [eval/results.md](eval/results.md) with no model: for the 16 decisions that have an invalidating document, does the method surface it?

| method | recall@5 of invalidating docs | decisions with ≥1 found |
|---|---|---|
| graph path query (Moot) | **1.00** | **100%** |
| BM25 top-5, query = decision title + summary | 0.81 | 81% |
| random 5 docs (control) | 0.01 | – |

`make eval-scale` reproduces [eval/results_scale.md](eval/results_scale.md), also with no model. It pads the corpus with up to 20,000 extra documents about the same systems, seeds a graph for each size, and measures recall and FalkorDB latency; then it scores verdicts against the ground truth and against a retrieval-only staleness heuristic.

| extra noise docs | graph recall@5 | BM25 recall@5 | audit p50 | full ledger | seed |
|---|---|---|---|---|---|
| 0 | **1.00** | 0.81 | 1.0 ms | 3 ms | 0.0 s |
| 1,000 | **1.00** | 0.81 | 1.1 ms | 3 ms | 0.0 s |
| 5,000 | **1.00** | 0.81 | 1.1 ms | 9 ms | 0.2 s |
| 20,000 | **1.00** | 0.81 | 1.1 ms | 3 ms | 0.6 s |

| verdicts (30 decisions) | exact | stale precision | stale recall | F1 |
|---|---|---|---|---|
| graph path rule (Moot) | **30/30** | **1.00** | **1.00** | **1.00** |
| BM25 top-5 + change-cue heuristic | – | 0.50 | 0.75 | 0.60 |

The audit is an index lookup plus a bounded path expansion, so its latency does not move with corpus size. The seed column is where FalkorDB taught us something: the first import matched edge endpoints without labels, which cannot use the per-label index and took three minutes at 20k documents; naming the labels on both ends brought it to under a second on an M-series Mac.

`make eval-e2e` (needs a key) runs the model-in-the-loop comparison: a BM25 RAG company brain asked "does this still hold?" against Moot's graph verdict, scored on verdict accuracy and whether the cited document is the true invalidating one. Results land in `eval/results_e2e.md`.

## Honest limits

- The corpus is synthetic. Larkspur, its people and its documents are invented. The 30 ADRs carry hand-written context, alternatives and consequences (`moot/corpus/prose.py`); PR bodies and chat threads are dressed from the same spec; the 150 background noise documents are templated from a seed. The committed `graph.json` is built from the ground-truth spec, not from the LLM extractor. `moot extract` runs the extractor over the same text so the two can be compared, and its span check drops any premise or relation whose quote is not literally in the source.
- A premise can expire without any document saying so. Moot only knows what was written down.
- Extraction misses premises that are implied rather than stated. Verdicts are only as good as the BECAUSE_OF edges.
- "Disputed" is a coarse rule (contradicted, then re-affirmed). It does not weigh evidence quality.
- BM25 is a fair but not state-of-the-art retrieval baseline; it was chosen so the eval reproduces without an embedding model.
- Reporting lines are taken as recorded. Moot routes an orphaned decision up the line as it stood when the owner left; if HR never updated the line (Lena still "reports to" Ada), Moot skips people who left rather than guessing a new manager.
- "What if" pretends one reason breaks at a time. It does not model partial breaks ("churn rises a little") or reasons nobody wrote down.
- The full-text resolver is keyword-based. A question that shares no words with a decision's title or summary returns "unknown entity" rather than a guess, by design.

## AI disclosure

Built with Claude (Claude Code) as a pair programmer under the author's direction: the graph model, verdict rules, query design and corpus spec were specified by the author; Claude wrote most of the code, the synthetic documents and this README from those specifications, and the author reviewed and tested every piece. The model inside the product (`claude-opus-5-5` by default) narrates and extracts; it never decides a verdict and never writes Cypher.

## License

MIT.
