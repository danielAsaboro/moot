"""People and teams as graph features: who knows why, what leaves with a person, bridges, and single points of failure.

Who knows why a decision was made: its owner of record, whoever wrote its ADR (or the PR that introduced it), and whoever
wrote dated evidence on any reason below it. Knowing is read from authorship, so a person who knows why but never wrote
anything down does not count; Moot says so wherever it reports these numbers.

The algorithms run on a scratch graph, never on the company graph. Moot reads who knows what with read-only queries and
writes that projection into a fresh named graph: every decision, every person still here (minus the person leaving, for a
departure), and one KNOWS edge (both directions) between each person and each decision they know. Then:

  algo.WCC          knowledge islands: decisions joined by the people who know them; an island with decisions and no
                    person left in it is knowledge that walks out of the door
  algo.betweenness  people through whom most knowledge paths run: the bridges between otherwise separate teams
                    (samplingSize above the node count and a fixed seed, so the same projection always gives the same ranking; tests/test_algorithms.py checks the people come out in NetworkX's order)

The scratch graph is deleted before the answer returns. (We first used GRAPH.COPY of the whole graph; on macOS the
embedded server's copy fork can deadlock, so the projection is built from rows instead, which also keeps it small.)
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager

from falkordb import Graph

from . import tools
from .tools import GATE_DEPTH, _q, today

PROJECT = ["Person", "Decision"]
KNOWLEDGE = ["KNOWS", "KNOWN_BY"]


def _active(left: str | None, as_of: str) -> bool:
    return not left or left > as_of


def knowers(g: Graph, decision_id: str, as_of: str | None = None) -> dict:
    """Who knows why `decision_id` was made, and in what capacity. bus_factor counts the people still here."""
    as_of = as_of or today()
    rows = _q(g,
        "MATCH (d:Decision {id: $id}) "
        "OPTIONAL MATCH (o:Person)-[w:OWNS]->(d) WHERE w.valid_from <= $as_of "
        "WITH d, collect(DISTINCT {id: o.id, name: o.name, left: o.left, how: 'owner', what: d.id}) AS a "
        "OPTIONAL MATCH (d)-[:RECORDED_IN]->(src:Evidence)<-[:AUTHORED]-(w2:Person) "
        "WITH d, a, collect(DISTINCT {id: w2.id, name: w2.name, left: w2.left, how: 'wrote the record', what: src.id}) AS b "
        "OPTIONAL MATCH (d)-[:BECAUSE_OF|DERIVED_FROM*1..%d]->(pr:Premise)<-[r:SUPPORTS|CONTRADICTS]-(e:Evidence)<-[:AUTHORED]-(w3:Person) "
        "WHERE r.at <= $as_of "
        "RETURN d.id, a, b, collect(DISTINCT {id: w3.id, name: w3.name, left: w3.left, how: 'wrote evidence on a reason', what: e.id, reason: pr.id})" % GATE_DEPTH,
        {"id": decision_id, "as_of": as_of}).result_set
    if not rows:
        return dict(found=False, decision_id=decision_id)
    people: dict[str, dict] = {}
    for x in rows[0][1] + rows[0][2] + rows[0][3]:
        if not x.get("id"):
            continue
        p = people.setdefault(x["id"], dict(id=x["id"], name=x["name"], active=_active(x["left"], as_of), left=x["left"] or None, roles=[]))
        role = dict(how=x["how"], what=x["what"]) | ({"reason": x["reason"]} if x.get("reason") else {})
        if role not in p["roles"]:
            p["roles"].append(role)
    ranked = sorted(people.values(), key=lambda p: (not p["active"], -len(p["roles"]), p["name"] or ""))
    return dict(found=True, decision_id=decision_id, as_of=as_of, people=ranked, bus_factor=sum(1 for p in ranked if p["active"]))


KNOWERS = [
    "MATCH (p:Person)-[o:OWNS]->(d:Decision) WHERE o.valid_from <= $as_of RETURN DISTINCT p.id, d.id",
    "MATCH (p:Person)-[:AUTHORED]->(:Evidence)<-[:RECORDED_IN]-(d:Decision) RETURN DISTINCT p.id, d.id",
    "MATCH (p:Person)-[:AUTHORED]->(:Evidence)-[r:SUPPORTS|CONTRADICTS]->(:Premise)<-[:BECAUSE_OF|DERIVED_FROM*1..%d]-(d:Decision) "
    "WHERE r.at <= $as_of RETURN DISTINCT p.id, d.id" % GATE_DEPTH,
]


@contextmanager
def knowledge_copy(g: Graph, as_of: str, without: tuple[str, ...] = ()):
    """A scratch graph with the KNOWS projection of `g` on `as_of`, minus people gone by then (and `without`); deleted after."""
    people = [dict(id=i, name=n, role=r) for i, n, r, left in
              _q(g, "MATCH (p:Person) RETURN p.id, p.name, p.role, p.left").result_set if _active(left, as_of) and i not in without]
    here = {p["id"] for p in people}
    decisions = [r[0] for r in _q(g, "MATCH (d:Decision) RETURN d.id").result_set]
    pairs = sorted({(p, d) for q in KNOWERS for p, d in _q(g, q, {"as_of": as_of}).result_set if p in here})
    c = Graph(g.client, f"{g.name}__people_{uuid.uuid4().hex[:10]}")  # same server and credentials as g
    try:
        _q(c, "UNWIND $ds AS id CREATE (:Decision {id: id})", {"ds": decisions}, write=True)
        _q(c, "UNWIND $ps AS p CREATE (:Person {id: p.id, name: p.name, role: p.role})", {"ps": people}, write=True)
        _q(c, "CREATE INDEX FOR (n:Person) ON (n.id)", write=True)
        _q(c, "CREATE INDEX FOR (n:Decision) ON (n.id)", write=True)
        _q(c, "UNWIND $pairs AS x MATCH (p:Person {id: x[0]}), (d:Decision {id: x[1]}) CREATE (p)-[:KNOWS]->(d), (d)-[:KNOWN_BY]->(p)",
           {"pairs": [list(x) for x in pairs]}, write=True)
        yield c
    finally:
        c.delete()


def islands(c: Graph) -> list[dict]:
    rows = _q(c,
        "CALL algo.WCC({nodeLabels: $labels, relationshipTypes: $rels}) YIELD node, componentId "
        "RETURN componentId, collect(CASE WHEN node:Decision THEN node.id END), collect(CASE WHEN node:Person THEN node.id END)",
        {"labels": PROJECT, "rels": KNOWLEDGE}).result_set
    return [dict(component=cid, decisions=sorted(x for x in ds if x), people=sorted(x for x in ps if x)) for cid, ds, ps in rows]


def _live(g: Graph, as_of: str) -> dict[str, dict]:
    return {r["id"]: r for r in tools.ledger(g, as_of, 4) if r["verdict"] != "RETIRED"}


def departure(g: Graph, person_id: str, as_of: str | None = None) -> dict:
    """What leaves with a person: live decisions nobody else still here knows the reasons for, the reasons only they wrote
    evidence on, and the systems those decisions govern. Computed on the scratch projection with the person removed."""
    as_of = as_of or today()
    who = _q(g, "MATCH (p:Person {id: $id}) RETURN p", {"id": person_id}).result_set
    if not who:
        return dict(found=False, person_id=person_id)
    person = tools._node(who[0][0])
    live = _live(g, as_of)
    with knowledge_copy(g, as_of) as c:  # the projection as it stands, then without the person
        before = {d for i in islands(c) if not i["people"] for d in i["decisions"]}
        _q(c, "MATCH (p:Person {id: $id}) DETACH DELETE p", {"id": person_id}, write=True)
        after_islands = islands(c)
    after = {d for i in after_islands if not i["people"] for d in i["decisions"]}
    leaving = sorted(d for d in after - before if d in live)
    reasons = _q(g,
        "MATCH (pr:Premise)<-[r:SUPPORTS|CONTRADICTS]-(e:Evidence) WHERE r.at <= $as_of "
        "OPTIONAL MATCH (a:Person)-[:AUTHORED]->(e) "
        "WITH pr, collect(DISTINCT CASE WHEN a.left = '' OR a.left > $as_of THEN a.id END) AS here, collect(DISTINCT e.id) AS docs "
        "WHERE here = [$id] "
        "OPTIONAL MATCH (d:Decision)-[:BECAUSE_OF|DERIVED_FROM*1..%d]->(pr) "
        "RETURN pr.id, pr.text, docs, collect(DISTINCT d.id)" % GATE_DEPTH, {"as_of": as_of, "id": person_id}).result_set
    only_reasons = [dict(id=pid, text=text, evidence=sorted(docs), decisions=sorted(x for x in ds if x in live)) for pid, text, docs, ds in reasons]
    owned = sorted(did for did, r in live.items() if r.get("owner_id") == person_id and r.get("owner_active"))
    systems_all: dict[str, set] = {}
    for did, r in live.items():
        for s in r["systems"]:
            systems_all.setdefault(s, set()).add(did)
    systems = sorted(s for s, ds in systems_all.items() if ds and ds <= set(leaving))
    succ = tools.successor(g, person_id, as_of, as_of) if owned else None
    return dict(found=True, person=person, as_of=as_of, active=_active(person.get("left"), as_of),
                leaves=[dict(id=d, title=live[d]["title"], verdict=live[d]["verdict"], systems=live[d]["systems"]) for d in leaving],
                only_they_evidence=only_reasons, owned=[dict(id=d, title=live[d]["title"], verdict=live[d]["verdict"]) for d in owned],
                systems_nobody_else_explains=systems, successor=succ,
                islands_after=len(after_islands), method="KNOWS projection in a scratch graph, remove the person, algo.WCC")


def people(g: Graph, as_of: str | None = None) -> dict:
    """Every person still here: what they own, what they know, where they are the only one who knows, and how much
    knowledge runs through them (betweenness on the KNOWS projection). Plus the bus factor of every live decision."""
    as_of = as_of or today()
    live = _live(g, as_of)
    with knowledge_copy(g, as_of) as c:
        isl = islands(c)
        bet = dict(_q(c, "CALL algo.betweenness({nodeLabels: $labels, relationshipTypes: $rels, samplingSize: 10000, samplingSeed: 7}) YIELD node, score "
                         "WHERE node:Person RETURN node.id, score", {"labels": PROJECT, "rels": KNOWLEDGE}).result_set)
        know = _q(c, "MATCH (p:Person)-[:KNOWS]->(d:Decision) RETURN p.id, p.name, p.role, collect(DISTINCT d.id)").result_set
        everyone = _q(c, "MATCH (p:Person) RETURN p.id, p.name, p.role").result_set
    knows = {pid: [d for d in ds if d in live] for pid, _, _, ds in know}
    by_dec: dict[str, set] = {d: set() for d in live}
    for pid, ds in knows.items():
        for d in ds:
            by_dec[d].add(pid)
    out = []
    for pid, name, role in everyone:
        ds = knows.get(pid, [])
        sole = sorted(d for d in ds if by_dec[d] == {pid})
        owned = sorted(d for d, r in live.items() if r.get("owner_id") == pid and r.get("owner_active"))
        out.append(dict(id=pid, name=name, role=role, knows=len(ds), owns=owned, sole=sole, betweenness=round(bet.get(pid, 0.0), 2)))
    out.sort(key=lambda p: (-len(p["sole"]), -p["betweenness"], -p["knows"], p["name"] or ""))
    bus = {d: len(ps) for d, ps in by_dec.items()}
    nobody = [i for i in isl if i["decisions"] and not i["people"]]
    return dict(as_of=as_of, people=out, bus_factor=dict(zero=sorted(d for d, n in bus.items() if n == 0),
                                                         one=sorted(d for d, n in bus.items() if n == 1),
                                                         more=sum(1 for n in bus.values() if n > 1)),
                islands=len([i for i in isl if i["decisions"]]), orphaned_islands=[i["decisions"] for i in nobody],
                method="KNOWS projection in a scratch graph, algo.WCC + algo.betweenness")


def premise_spof(g: Graph, as_of: str | None = None, limit: int = 10) -> dict:
    """Single points of failure among reasons: a reason two or more live decisions rest on, vouched for by at most one
    document or by at most one person still here."""
    as_of = as_of or today()
    live = _live(g, as_of)
    rows = _q(g,
        "MATCH (d:Decision)-[:BECAUSE_OF|DERIVED_FROM*1..%d]->(pr:Premise) "
        "WITH pr, collect(DISTINCT d.id) AS ds "
        "OPTIONAL MATCH (e)-[r:SUPPORTS|CONTRADICTS]->(pr) WHERE r.at <= $as_of "
        "OPTIONAL MATCH (a:Person)-[:AUTHORED]->(e) "
        "RETURN pr.id, pr.text, ds, collect(DISTINCT e.id), collect(DISTINCT CASE WHEN a.left = '' OR a.left > $as_of THEN a.name END), "
        "collect(DISTINCT {rel: type(r), at: r.at}), pr.advisory" % GATE_DEPTH, {"as_of": as_of}).result_set
    out = []
    for pid, text, ds, docs, authors, ev, advisory in rows:
        ds = sorted(d for d in ds if d in live)
        docs = sorted(x for x in docs if x)
        authors = sorted(x for x in authors if x)
        if len(ds) < 2 or (len(docs) > 1 and len(authors) > 1):
            continue
        state = tools.premise_state([e for e in ev if e.get("at")], bool(advisory))
        why = "no evidence at all" if not docs else f"one document ({docs[0]})" if len(docs) == 1 else \
            f"one person still here ({authors[0]})" if len(authors) == 1 else "no one still here wrote its evidence"
        out.append(dict(id=pid, text=text, state=state, decisions=ds, evidence=docs, people=authors, why=why))
    out.sort(key=lambda x: (-len(x["decisions"]), len(x["evidence"]), x["id"]))
    return dict(as_of=as_of, reasons=out[:limit], total=len(out))
