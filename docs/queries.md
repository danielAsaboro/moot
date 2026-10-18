# The full query catalogue

Every parameterised Cypher query Moot runs, with the reasoning behind each. The README carries the key ones; this is the complete list (`moot/tools.py`).

The model never writes Cypher. These parameterised queries are the whole tool catalogue (`moot/tools.py`), exposed to the agent, the API and the MCP server.

**1. Entity resolution** (full-text index; the question's content words, OR-ed, prefix-matched)

```cypher
CALL db.idx.fulltext.queryNodes('Decision', $q) YIELD node, score
RETURN node.id, node.title, node.summary, node.decided_on, score ORDER BY score DESC LIMIT $limit
```

**2. The audit**: premises up to `depth` hops, with every dated event on each premise and the person who wrote it. This is the verdict.

```cypher
MATCH (d:Decision {id: $id})
MATCH p = (d)-[:BECAUSE_OF|DERIVED_FROM*1..4]->(pr:Premise)
OPTIONAL MATCH (e)-[r:SUPPORTS|CONTRADICTS]->(pr)          // Evidence, or an owner's ruling (Finding)
  WHERE r.at <= $as_of AND coalesce(r.stated, r.at) <= $as_of  // took effect and was stated by as_of
OPTIONAL MATCH (a:Person)-[:AUTHORED]->(e)
RETURN pr, nodes(p) AS pn, length(p) AS hops,
       collect({id: e.id, title: e.title, kind: e.kind, rel: type(r), at: r.at, stated: r.stated, quote: r.quote, author: a.name})
ORDER BY hops
```

Retirement is read in the same pass and is dated too, so time travel cannot retire a decision with a successor that does not exist yet:

```cypher
MATCH (d:Decision {id: $id})
OPTIONAL MATCH (n:Decision)-[su:SUPERSEDES]->(d) WHERE su.at <= $as_of
OPTIONAL MATCH (x:Evidence)-[rt:RETIRES]->(d) WHERE rt.at <= $as_of
RETURN d, n.id, n.title, su.at, x.id, x.title, rt.at, rt.quote
```

`nodes(p)` is returned with every answer and drawn in the UI as the path chain. `$as_of` makes the same question answer differently on different dates.

**2b. The agent gate**: query 2 (and the retirement read) at depth 6, then `gate()`. It returns `ALLOW | DENY | REVALIDATE`, the reasons with the premise, the evidence id and `nodes(p)` for each, and for ALLOW the supporting evidence. It never writes. Exposed as `GET /api/gate/{id}` (`?graph=public_adrs` for the real ADRs) and the MCP tool `check_action`, described to clients as "call before you enforce, rely on or renew a decision; only act on ALLOW". Each answer carries `snapshot: {graph, as_of, digest}`; the digest covers every row that can change this decision's gate on any date (premises to depth 6, every dated event, retirement, owners), so the same pair always gives the same verdict and a new digest means re-check. `tests/test_graph.py::test_api_mcp_and_tools_agree_at_the_boundary` asks the HTTP route, the MCP tool and the function the same question on the day before PR-412, the day itself and the day after, and requires byte-identical answers: the as-of cutoff is inclusive.

Read-only is enforced by the engine: every read is `GRAPH.RO_QUERY`, which FalkorDB refuses to run a write through. There is no keyword filter to get wrong.

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
MATCH (d:Decision)
OPTIONAL MATCH (n:Decision)-[su:SUPERSEDES]->(d) WHERE su.at <= $as_of
OPTIONAL MATCH (x:Evidence)-[rt:RETIRES]->(d) WHERE rt.at <= $as_of
WITH d, coalesce(n.id, x.id) AS sup
OPTIONAL MATCH p = (d)-[:BECAUSE_OF|DERIVED_FROM*1..4]->(pr:Premise)
OPTIONAL MATCH (e:Evidence)-[r:SUPPORTS|CONTRADICTS]->(pr) WHERE r.at <= $as_of
WITH d, sup, pr, collect({rel: type(r), at: r.at}) AS ev
OPTIONAL MATCH (d)-[:GOVERNS]->(s:System)
RETURN d, sup, pr.id, ev, collect(DISTINCT s.name) ORDER BY d.id
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

**The writes**, each behind an approval button. A handover is one `CREATE (p)-[:OWNS {valid_from: $as_of, valid_to: '', handed_over_from: $prev}]->(d)`. A verdict or re-open memo is a `Finding` that supersedes the previous finding for the decision and cites the evidence it relied on. An owner's ruling is a `Finding` with a dated `SUPPORTS` or `CONTRADICTS` edge to the premise; it is refused for a premise outside the decision or one that already has evidence that decides it.

```cypher
MATCH (d:Decision {id: $did})
OPTIONAL MATCH (prev:Finding)-[:ABOUT]->(d) WHERE NOT (prev)-[:SUPERSEDED_BY]->()
WITH d, collect(prev) AS prevs
CREATE (f:Finding {id: $fid, verdict: $verdict, as_of: $as_of, depth: $depth, created_at: $now})-[:ABOUT]->(d)
...  (prev)-[:SUPERSEDED_BY]->(f), (f)-[:CITES]->(e)
```

Also used: `algo.WCC` in tests and exploration to cluster decisions that share premises, and `db.idx.fulltext.createNodeIndex` for the indexes above.
