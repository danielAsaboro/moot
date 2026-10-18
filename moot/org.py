"""How people actually work together, against how the org chart says they do.

COLLAB: two people collaborate when they wrote the same record (a KEP's authors and approvers, an ADR's authors, a PR and
its reviewers); the weight is how many records they share. The projection goes into a scratch graph, never the company
graph, and is deleted before the answer returns. On it:

  algo.labelPropagation  communities of people who work together; set beside the teams they officially answer for, a
                         community spread over several teams with no team holding most of it is a hidden team
  algo.pageRank          who the collaboration network leans on
  algo.betweenness       who bridges otherwise separate groups
  algo.SPpaths           who connects A and B: the shortest chain of shared records between two people
"""
from __future__ import annotations

import uuid
from collections import Counter
from contextlib import contextmanager

from falkordb import Graph

from .tools import _q

LABELS, RELS = ["Person"], ["COLLAB"]


def collab_pairs(g: Graph) -> dict[tuple[str, str], list[str]]:
    """(person, person) -> the records both of them wrote, read from AUTHORED edges."""
    rows = _q(g, "MATCH (p:Person)-[:AUTHORED]->(e:Evidence)<-[:AUTHORED]-(q:Person) WHERE p.id < q.id "
                 "RETURN p.id, q.id, collect(DISTINCT e.id)").result_set
    return {(a, b): sorted(es) for a, b, es in rows}


def official_team(g: Graph) -> dict[str, str]:
    """The team a person officially answers for: the one they lead now, else the team owning most of what they wrote."""
    out = {p: t for p, t in _q(g, "MATCH (p:Person)-[l:LEADS]->(t:Team) WHERE coalesce(l.valid_to, '') = '' RETURN p.id, t.id").result_set}
    wrote: dict[str, Counter] = {}
    for p, t in _q(g, "MATCH (p:Person)-[:AUTHORED]->(:Evidence)<-[:RECORDED_IN]-(d:Decision)<-[:RESPONSIBLE_FOR]-(t:Team) "
                      "RETURN p.id, t.id").result_set:
        wrote.setdefault(p, Counter())[t] += 1
    for p, c in wrote.items():
        out.setdefault(p, c.most_common(1)[0][0])
    return out


@contextmanager
def collab_copy(g: Graph):
    pairs = collab_pairs(g)
    people = sorted({x for pair in pairs for x in pair})
    names = dict(_q(g, "MATCH (p:Person) RETURN p.id, p.name").result_set)
    c = Graph(g.client, f"{g.name}__collab_{uuid.uuid4().hex[:10]}")
    try:
        _q(c, "UNWIND $ps AS p CREATE (:Person {id: p[0], name: p[1]})", {"ps": [[p, names.get(p) or p] for p in people]}, write=True)
        _q(c, "CREATE INDEX FOR (n:Person) ON (n.id)", write=True)
        _q(c, "UNWIND $es AS e MATCH (a:Person {id: e[0]}), (b:Person {id: e[1]}) "
              "CREATE (a)-[:COLLAB {w: e[2]}]->(b), (b)-[:COLLAB {w: e[2]}]->(a)",
           {"es": [[a, b, len(r)] for (a, b), r in pairs.items()]}, write=True)
        yield c, pairs, names
    finally:
        c.delete()


def hidden_teams(g: Graph, min_size: int = 3) -> dict:
    """Communities of collaborators (label propagation) set beside the teams people officially answer for."""
    team = official_team(g)
    tname = dict(_q(g, "MATCH (t:Team) RETURN t.id, t.name").result_set)
    with collab_copy(g) as (c, pairs, names):
        comm = _q(c, "CALL algo.labelPropagation({nodeLabels: $l, relationshipTypes: $r, maxIterations: 50}) YIELD node, communityId "
                     "RETURN node.id, communityId", {"l": LABELS, "r": RELS}).result_set
        rank = dict(_q(c, "CALL algo.pageRank('Person', 'COLLAB') YIELD node, score RETURN node.id, score").result_set)
        bet = dict(_q(c, "CALL algo.betweenness({nodeLabels: $l, relationshipTypes: $r, samplingSize: 100000, samplingSeed: 7}) "
                         "YIELD node, score RETURN node.id, score", {"l": LABELS, "r": RELS}).result_set)
    groups: dict[int, list[str]] = {}
    for pid, cid in comm:
        groups.setdefault(cid, []).append(pid)
    out = []
    for members in groups.values():
        if len(members) < min_size:
            continue
        teams = Counter(team.get(p, "none") for p in members)
        top, n = teams.most_common(1)[0]
        share = n / len(members)
        out.append(dict(size=len(members), teams={tname.get(t, t): k for t, k in teams.most_common()},
                        main_team=tname.get(top, top), main_share=round(share, 2), hidden=share < 0.6 and len(teams) > 1,
                        hub=names.get(max(members, key=lambda p: rank.get(p, 0)), ""),
                        members=sorted((names.get(p) or p) for p in members)[:30]))
    out.sort(key=lambda x: (not x["hidden"], -x["size"]))
    bridges = sorted(bet, key=lambda p: -bet[p])[:10]
    return dict(communities=out, hidden=sum(1 for x in out if x["hidden"]), people=len(rank), pairs=len(pairs),
                bridges=[dict(id=p, name=names.get(p) or p, betweenness=round(bet[p], 1)) for p in bridges],
                method="COLLAB projection (people who wrote the same record) in a scratch graph; algo.labelPropagation, algo.pageRank, algo.betweenness")


def connection(g: Graph, a: str, b: str, max_len: int = 6) -> dict:
    """Who connects a and b: the shortest chain of people who wrote records together, with the records at each step."""
    with collab_copy(g) as (c, pairs, names):
        rows = _q(c, "MATCH (x:Person {id: $a}), (y:Person {id: $b}) "
                     "CALL algo.SPpaths({sourceNode: x, targetNode: y, relTypes: ['COLLAB'], maxLen: $n, pathCount: 1}) "
                     "YIELD path RETURN [n IN nodes(path) | n.id]", {"a": a, "b": b, "n": max_len}).result_set
    if not rows:
        return dict(found=False, a=a, b=b, why=f"no chain of shared records within {max_len} people")
    chain = rows[0][0]
    steps = [dict(frm=names.get(x) or x, to=names.get(y) or y, records=pairs.get(tuple(sorted((x, y))), [])[:5])
             for x, y in zip(chain, chain[1:])]
    return dict(found=True, a=a, b=b, people=[names.get(x) or x for x in chain], hops=len(chain) - 1, steps=steps,
                method="algo.SPpaths over the COLLAB projection")
