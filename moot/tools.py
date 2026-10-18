"""The fixed catalogue of read-only graph tools.

Every tool is a parameterised Cypher query run with ro_query. The language model never
writes Cypher and never sees the database. Tools return plain dicts that the API, the MCP
server and the agent all share. Paths are returned as node lists so the UI can show them.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from contextvars import ContextVar
from datetime import date, datetime, timezone

from falkordb import Graph

from .verdict import decision_verdict, event_order, gate, premise_state

# Query tracing: the UI's "show the Cypher" view. Every read goes through _q, which records the
# query text, its parameters, the row count and the FalkorDB round-trip time while a trace is open.
_trace: ContextVar[list | None] = ContextVar("moot_trace", default=None)


def start_trace() -> None:
    _trace.set([])


def end_trace() -> list[dict]:
    t = _trace.get() or []
    _trace.set(None)
    return t


def _q(g: Graph, cypher: str, params: dict | None = None, write: bool = False):
    t0 = time.perf_counter()
    res = g.query(cypher, params) if write else g.ro_query(cypher, params)
    tr = _trace.get()
    if tr is not None:
        tr.append(dict(cypher=cypher, params=params or {}, rows=len(res.result_set), ms=round((time.perf_counter() - t0) * 1000, 2),
                       write=write, graph=g.name))
    return res


# An event counts on `as_of` only once it had both taken effect and been stated: "valid at T, as known at K".
# Edges without a `stated` date were stated the day they took effect.
KNOWN = "r.at <= $as_of AND coalesce(r.stated, r.at) <= $as_of"

STOP = set("why do we does the a an of in on at to for is are our it this that still and or with by from have has".split())


def _node(n) -> dict:
    d = dict(n.properties)
    d["label"] = n.labels[0] if n.labels else ""
    return d


def _path_ids(nodes) -> list[dict]:
    return [dict(id=n.properties.get("id"), label=n.labels[0], title=n.properties.get("title") or n.properties.get("text") or n.properties.get("name")) for n in nodes]


def today() -> str:
    return date.today().isoformat()


# 1. Entity resolution: question -> candidate decisions, via the full-text index.
def find_decision(g: Graph, query: str, limit: int = 5) -> list[dict]:
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in STOP and len(w) > 2]
    if not words:
        return []
    ft = " | ".join(f"{w}*" for w in words)
    rows = _q(g, 
        "CALL db.idx.fulltext.queryNodes('Decision', $q) YIELD node, score "
        "RETURN node.id, node.title, node.summary, node.decided_on, score ORDER BY score DESC LIMIT $limit",
        {"q": ft, "limit": limit * 3}).result_set
    out = []
    for r in rows:
        hay = f"{r[1]} {r[2]}".lower()
        hits = sum(1 for w in words if w in hay)
        out.append(dict(id=r[0], title=r[1], summary=r[2], decided_on=r[3], score=r[4], matched_terms=hits))
    # rank by how many distinct question terms the decision covers, then by the index score
    return sorted(out, key=lambda c: (-c["matched_terms"], -c["score"]))


# 2. The audit: decision -> premises (up to `depth` hops) -> dated evidence -> verdict.
def audit_decision(g: Graph, decision_id: str, as_of: str | None = None, depth: int = 4) -> dict:
    as_of = as_of or today()
    depth = max(1, min(int(depth), 6))
    # Retirement is dated like everything else: a later decision that SUPERSEDES this one, or a document that RETIRES it
    # (the ADR's own status change, when the successor is outside the graph). Neither counts before its `at`.
    head = _q(g,
        "MATCH (d:Decision {id: $id}) "
        "OPTIONAL MATCH (n:Decision)-[su:SUPERSEDES]->(d) WHERE su.at <= $as_of AND coalesce(su.stated, su.at) <= $as_of "
        "OPTIONAL MATCH (x:Evidence)-[rt:RETIRES]->(d) WHERE rt.at <= $as_of AND coalesce(rt.stated, rt.at) <= $as_of "
        "OPTIONAL MATCH (d)-[:RECORDED_IN]->(src:Evidence) OPTIONAL MATCH (d)-[:GOVERNS]->(s:System) "
        "RETURN d, n.id, n.title, su.at, x.id, x.title, rt.at, rt.quote, src, collect(DISTINCT s.name)",
        {"id": decision_id, "as_of": as_of}).result_set
    if not head:
        return dict(found=False, decision_id=decision_id, verdict="NOT_IN_GRAPH")
    d, sup_id, sup_title, sup_at, ret_id, ret_title, ret_at, ret_quote, src, systems = head[0]
    superseded_by = (dict(id=sup_id, title=sup_title, at=sup_at, kind="decision") if sup_id else
                     dict(id=ret_id, title=ret_title, at=ret_at, kind="document", quote=ret_quote) if ret_id else None)
    if d.properties.get("decided_on", "") > as_of:
        return dict(found=True, decision=_node(d), as_of=as_of, depth=depth, verdict="NOT_YET", premises=[], superseded_by=None,
                    source=(_node(src) if src else None), systems=systems, owner=decision_owner(g, decision_id, as_of))
    rows = _q(g,
        "MATCH (d:Decision {id: $id}) MATCH p = (d)-[:BECAUSE_OF|DERIVED_FROM*1..%d]->(pr:Premise) "
        "OPTIONAL MATCH (e)-[r:SUPPORTS|CONTRADICTS]->(pr) WHERE %s "
        "OPTIONAL MATCH (a:Person)-[:AUTHORED]->(e) "
        "RETURN pr, nodes(p) AS pn, length(p) AS hops, "
        "collect({id: e.id, title: e.title, kind: e.kind, date: e.date, rel: type(r), at: r.at, stated: r.stated, quote: r.quote, author: a.name}) "
        "ORDER BY hops" % (depth, KNOWN), {"id": decision_id, "as_of": as_of}).result_set
    premises, seen = [], set()
    for pr, path_nodes, _hops, events in rows:
        pid = pr.properties["id"]
        if pid in seen:
            continue
        seen.add(pid)
        uniq: dict = {}  # one row per event, however many people authored it
        for e in events:
            if e.get("id"):
                k = (e["id"], e["rel"], e["at"])
                if k in uniq and e.get("author") and uniq[k].get("author") and e["author"] not in uniq[k]["author"]:
                    uniq[k]["author"] += f", {e['author']}"
                uniq.setdefault(k, e)
        events = list(uniq.values())
        for e in events:
            if e.get("stated") is None:
                e.pop("stated", None)
        unchecked = pr.properties.get("unchecked") or None
        # a premise nobody could check, with no dated evidence either way, is reported as unchecked, not as holding
        state = "unchecked" if unchecked and not events else premise_state(events, bool(pr.properties.get("advisory")))
        premises.append(dict(id=pid, text=pr.properties["text"], kind=pr.properties.get("kind"), hops=len(path_nodes) - 1,
                             path=_path_ids(path_nodes), state=state, unchecked=unchecked,
                             evidence=sorted(events, key=event_order),
                             contradicted_before_decision=any(e["rel"] == "CONTRADICTS" and e["at"] < d.properties["decided_on"] for e in events),
                             # a reason read from the ADR's own words carries its provenance (moot/connectors/reasons.py)
                             **{k: pr.properties[k] for k in ("quote", "section", "source", "extracted_by") if pr.properties.get(k)}))
    verdict = decision_verdict(premises, superseded=bool(superseded_by))
    return dict(found=True, decision=_node(d), as_of=as_of, depth=depth, verdict=verdict, premises=premises,
                superseded_by=superseded_by, source=(_node(src) if src else None), systems=systems,
                owner=decision_owner(g, decision_id, as_of), team=decision_team(g, decision_id, as_of))


# 2a. Since when? The verdict can only change on a date something in the decision's subgraph happened, so the audit is
#     re-run on each of those dates and the history is the runs of equal verdicts. `since` is when the current one began.
def verdict_history(g: Graph, decision_id: str, as_of: str | None = None, depth: int = 4) -> dict:
    as_of = as_of or today()
    depth = max(1, min(int(depth), 6))
    rows = _q(g,
        "MATCH (d:Decision {id: $id}) "
        "OPTIONAL MATCH (x)-[rt:SUPERSEDES|RETIRES]->(d) "
        "OPTIONAL MATCH (d)-[:BECAUSE_OF|DERIVED_FROM*1..%d]->(pr:Premise)<-[r:SUPPORTS|CONTRADICTS]-() "
        "RETURN d.decided_on, collect(DISTINCT rt.at) + collect(DISTINCT rt.stated) + collect(DISTINCT r.at) + collect(DISTINCT r.stated)" % depth,
        {"id": decision_id}).result_set
    if not rows:
        return dict(found=False, decision_id=decision_id)
    decided, dates = rows[0]
    dates = sorted({x for x in [decided, *dates] if x and x <= as_of})
    history: list[dict] = []
    for x in dates:
        v = audit_decision(g, decision_id, x, depth)["verdict"]
        if not history or history[-1]["verdict"] != v:
            history.append(dict(verdict=v, since=x))
    current = audit_decision(g, decision_id, as_of, depth)["verdict"]
    if not history or history[-1]["verdict"] != current:  # e.g. NOT_YET before the decision date
        history.append(dict(verdict=current, since=None))
    return dict(found=True, decision_id=decision_id, as_of=as_of, depth=depth, verdict=current, since=history[-1]["since"], history=history)


# 2b. The validity gate: may an agent act on (enforce, rely on, renew) this decision? Always audited at full depth,
#     because a shallow audit lets a decision through whose reason died two hops down (D01 at depth 1).
GATE_DEPTH = 6


def check_action(g: Graph, decision_id: str, as_of: str | None = None) -> dict:
    a = audit_decision(g, decision_id, as_of, GATE_DEPTH)
    as_of = a.get("as_of") or as_of or today()
    out = gate(a, coverage(g))
    return dict(out, decision_id=decision_id, title=a["decision"]["title"] if a.get("found") else None,
                as_of=as_of, depth=GATE_DEPTH, snapshot=snapshot(g, decision_id, as_of), route=route(g, a) if out["gate"] != "ALLOW" else None)


def route(g: Graph, a: dict) -> dict | None:
    """Who a blocked agent should ask: the owner of record if still here; else whoever the owner reported to the day they left
    (REPORTS_TO, skipping people who also left); else the leads of the team that answers for the decision on that date
    (Team / LEADS); else nobody on record, which is itself the finding."""
    o = a.get("owner")
    if o and o.get("active"):
        return dict(to="owner", people=[dict(id=o["id"], name=o["name"])], why=f"{o['name']} owns it")
    if o and o.get("valid_to"):
        s = successor(g, o["id"], o["valid_to"], a.get("as_of"))
        if s:
            return dict(to="successor", people=[dict(id=s["id"], name=s["name"], role=s["role"])],
                        why=f"{o['name']} owned it and left on {o['valid_to']}; {s['name']} is next up their reporting line")
    t = a.get("team")
    if t and t.get("leads"):
        return dict(to="team", team=t["name"], people=[dict(id=x["id"], name=x["name"], role=x["role"]) for x in t["leads"]],
                    why=f"{t['name']} answers for it" + (f"; its owner of record, {o['name']}, has left" if o else ""))
    return dict(to=None, people=[], why="nobody on record answers for it: no active owner and no team named")


def coverage(g: Graph) -> dict:
    """How much the graph could vouch for at all. An empty or mis-pointed graph must not read as 'nothing contradicts it'."""
    r = _q(g, "MATCH (d:Decision) WITH count(d) AS n OPTIONAL MATCH ()-[e:SUPPORTS|CONTRADICTS]->(:Premise) RETURN n, count(e)").result_set
    return dict(decisions=r[0][0], evidence_edges=r[0][1])


def _digest(rows) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()[:16]


def decision_digest(g: Graph, decision_id: str) -> str:
    """A digest of every row that can change this decision's gate on any date: the decision, what retires it, its premises
    to full depth with their paths, every dated event on them (all dates, not just up to as_of), and its owners.
    The same (digest, as_of) pair always gives the same verdict; a new digest means the decision needs re-checking."""
    rows = _q(g,
        "MATCH (d:Decision {id: $id}) "
        "OPTIONAL MATCH (x)-[rt:SUPERSEDES|RETIRES]->(d) "
        "WITH d, collect([x.id, type(rt), properties(rt)]) AS ret "
        "OPTIONAL MATCH (o:Person)-[w:OWNS]->(d) "
        "WITH d, ret, collect([o.id, o.left, properties(w)]) AS own "
        "OPTIONAL MATCH p = (d)-[:BECAUSE_OF|DERIVED_FROM*1..%d]->(pr:Premise) "
        "OPTIONAL MATCH (e)-[r:SUPPORTS|CONTRADICTS]->(pr) "
        "RETURN properties(d), ret, own, [n IN nodes(p) | n.id], properties(pr), collect([e.id, e.kind, type(r), properties(r)])" % GATE_DEPTH,
        {"id": decision_id}).result_set
    if not rows:
        return _digest(["absent", decision_id])
    canon = lambda xs: sorted((x for x in xs if x and x[0] is not None), key=lambda x: json.dumps(x, sort_keys=True, default=str))
    head = [rows[0][0], canon(rows[0][1]), canon(rows[0][2])]
    body = sorted(([path, pr, canon(ev)] for _, _, _, path, pr, ev in rows if path), key=lambda x: json.dumps(x, sort_keys=True, default=str))
    return _digest([head, body])


def graph_digest(g: Graph) -> str:
    """A digest of the whole graph: every node and edge with its properties. Changes on any write, Findings included."""
    nodes = _q(g, "MATCH (n) RETURN labels(n)[0], properties(n)").result_set
    edges = _q(g, "MATCH (a)-[r]->(b) RETURN a.id, type(r), b.id, properties(r)").result_set
    key = lambda x: json.dumps(x, sort_keys=True, default=str)
    return _digest([sorted(nodes, key=key), sorted(edges, key=key)])


def snapshot(g: Graph, decision_id: str, as_of: str) -> dict:
    return dict(graph=g.name, as_of=as_of, digest=decision_digest(g, decision_id))


# 3. Shared-premise impact: everything downstream of a premise, ranked by PageRank over the dependency graph.
def premise_impact(g: Graph, premise_id: str) -> dict:
    rows = _q(g, 
        "MATCH (pr:Premise {id: $id}) MATCH p = (d:Decision)-[:BECAUSE_OF|DERIVED_FROM*1..6]->(pr) "
        "OPTIONAL MATCH (d)-[:GOVERNS]->(s:System) "
        "RETURN DISTINCT d.id, d.title, length(p), collect(DISTINCT s.name)", {"id": premise_id}).result_set
    rank = {r[0]: r[1] for r in _q(g, 
        "CALL algo.pageRank(null, null) YIELD node, score WHERE node:Premise RETURN node.id, score").result_set}
    pr = _q(g, "MATCH (pr:Premise {id: $id}) OPTIONAL MATCH (pr)-[:DERIVED_FROM]->(up:Premise) RETURN pr, up.id, up.text",
                    {"id": premise_id}).result_set
    if not pr:
        return dict(found=False, premise_id=premise_id)
    systems = sorted({s for r in rows for s in r[3]})
    return dict(found=True, premise=_node(pr[0][0]), derived_from=(dict(id=pr[0][1], text=pr[0][2]) if pr[0][1] else None),
                pagerank=rank.get(premise_id), decisions=[dict(id=r[0], title=r[1], hops=r[2], systems=r[3]) for r in rows],
                systems=systems)


# 4. New document -> which decisions can it reach? Shortest paths from the evidence node.
def trace_document(g: Graph, evidence_id: str, max_len: int = 6) -> dict:
    ev = _q(g, "MATCH (e:Evidence {id: $id}) RETURN e", {"id": evidence_id}).result_set
    if not ev:
        return dict(found=False, evidence_id=evidence_id)
    rows = _q(g, 
        "MATCH (e:Evidence {id: $id}), (d:Decision) "
        "CALL algo.SPpaths({sourceNode: e, targetNode: d, relTypes: ['CONTRADICTS','SUPPORTS','BECAUSE_OF','DERIVED_FROM'], "
        "relDirection: 'both', maxLen: $max, pathCount: 1}) YIELD path "
        "RETURN d.id, d.title, length(path), nodes(path)", {"id": evidence_id, "max": max_len}).result_set
    return dict(found=True, evidence=_node(ev[0][0]),
                reaches=[dict(id=r[0], title=r[1], hops=r[2], path=_path_ids(r[3])) for r in sorted(rows, key=lambda r: r[2])])


# 5. Who owns it, as of a date. Ownership edges carry validity windows; a handover adds a newer OWNS edge.
def owners_as_of(g: Graph, as_of: str | None = None, decision_id: str | None = None) -> dict[str, dict]:
    """decision id -> the owner of record on `as_of`: the OWNS edge with the latest valid_from on or before that date."""
    as_of = as_of or today()
    rows = _q(g,
        "MATCH (p:Person)-[o:OWNS]->(d:Decision) WHERE o.valid_from <= $as_of AND ($id IS NULL OR d.id = $id) "
        "RETURN d.id, p.id, p.name, p.role, o.valid_from, o.valid_to, o.handed_over_from ORDER BY d.id, o.valid_from",
        {"as_of": as_of, "id": decision_id}).result_set
    out: dict[str, dict] = {}
    for did, pid, name, role, vf, vt, prev in rows:
        out[did] = dict(id=pid, name=name, role=role, valid_from=vf, valid_to=vt or None, active=(not vt) or vt >= as_of,
                        handed_over_from=prev or None)
    return out


def decision_owner(g: Graph, decision_id: str, as_of: str | None = None) -> dict | None:
    return owners_as_of(g, as_of, decision_id).get(decision_id)


# 5b. Which team answers for a decision on `as_of`, and who leads that team then (Team / LEADS from sigs.yaml or CODEOWNERS).
def decision_team(g: Graph, decision_id: str, as_of: str | None = None) -> dict | None:
    as_of = as_of or today()
    rows = _q(g,
        "MATCH (t:Team)-[r:RESPONSIBLE_FOR]->(:Decision {id: $id}) WHERE coalesce(r.valid_from, '') <= $as_of "
        "OPTIONAL MATCH (p:Person)-[l:LEADS]->(t) "
        "OPTIONAL MATCH (t)-[:RUNS]->(pj:Project) "
        "RETURN t.id, t.name, t.source, collect(DISTINCT {id: p.id, name: p.name, role: l.role, from: l.valid_from, to: l.valid_to}), count(DISTINCT pj)",
        {"id": decision_id, "as_of": as_of}).result_set
    if not rows:
        return None
    tid, name, source, leads, projects = rows[0]
    leads = [x for x in leads if x.get("id")]
    now = [x for x in leads if x["from"] <= as_of and (not x["to"] or x["to"] > as_of)]
    before = [x for x in leads if x["to"] and x["to"] <= as_of]
    return dict(id=tid, name=name, source=source, projects=projects,
                leads=sorted(now, key=lambda x: (x["role"], x["name"])), former=sorted(before, key=lambda x: x["to"]))


# 6. The ledger: every decision with its verdict, in one pass.
def ledger(g: Graph, as_of: str | None = None, depth: int = 4) -> list[dict]:
    as_of = as_of or today()
    depth = max(1, min(int(depth), 6))
    rows = _q(g, 
        "MATCH (d:Decision) "
        "OPTIONAL MATCH (n:Decision)-[su:SUPERSEDES]->(d) WHERE su.at <= $as_of AND coalesce(su.stated, su.at) <= $as_of "
        "OPTIONAL MATCH (x:Evidence)-[rt:RETIRES]->(d) WHERE rt.at <= $as_of AND coalesce(rt.stated, rt.at) <= $as_of "
        "WITH d, coalesce(n.id, x.id) AS sup "
        "OPTIONAL MATCH p = (d)-[:BECAUSE_OF|DERIVED_FROM*1..%d]->(pr:Premise) "
        "OPTIONAL MATCH (e)-[r:SUPPORTS|CONTRADICTS]->(pr) WHERE %s "
        "WITH d, sup, pr, collect({rel: type(r), at: r.at, stated: r.stated, kind: e.kind}) AS ev "
        "OPTIONAL MATCH (d)-[:GOVERNS]->(s:System) "
        "RETURN d, sup, pr.id, ev, collect(DISTINCT s.name), pr.advisory ORDER BY d.id" % (depth, KNOWN),
        {"as_of": as_of}).result_set
    owners = owners_as_of(g, as_of)
    out: dict[str, dict] = {}
    for d, sup, pid, ev, systems, advisory in rows:
        did = d.properties["id"]
        if d.properties.get("decided_on", "") > as_of:
            continue  # not decided yet as of that date
        o = owners.get(did)
        item = out.setdefault(did, dict(_node(d), superseded=bool(sup), premises={}, owner=o["name"] if o else None,
                                        owner_id=o["id"] if o else None, owner_active=bool(o and o["active"]), systems=systems))
        if pid:
            item["premises"][pid] = premise_state([e for e in ev if e.get("at")], bool(advisory))
    result = []
    for item in out.values():
        states = [dict(state=s) for s in item.pop("premises").values()]
        item["verdict"] = decision_verdict(states, item.pop("superseded"))
        item["expired_premises"] = sum(1 for s in states if s["state"] == "expired")
        result.append(item)
    order = {"MOOT": 0, "DISPUTED": 1, "UNDOCUMENTED": 2, "HOLDS": 3, "RETIRED": 4}
    return sorted(result, key=lambda r: (order[r["verdict"]], r["id"]))


# 7. The rot curve: the ledger re-run at month ends, so the UI can show verdicts drifting over time. One query reads every
# dated event once; the month ends then apply the ledger's own rule (KNOWN, the verdict functions) to those rows, so a
# timeline is one round trip instead of one per month. tests/test_graph.py checks it against ledger() at every month end.
def _known(e: dict, as_of: str) -> bool:
    return bool(e.get("at")) and e["at"] <= as_of and (e.get("stated") or e["at"]) <= as_of


def timeline(g: Graph, start: str = "2025-01-01", end: str | None = None, depth: int = 4) -> list[dict]:
    end = end or today()
    depth = max(1, min(int(depth), 6))
    rows = _q(g,
        "MATCH (d:Decision) "
        "OPTIONAL MATCH (:Decision)-[su:SUPERSEDES]->(d) "
        "OPTIONAL MATCH (:Evidence)-[rt:RETIRES]->(d) "
        "WITH d, collect(DISTINCT {at: su.at, stated: su.stated}) + collect(DISTINCT {at: rt.at, stated: rt.stated}) AS ends "
        "OPTIONAL MATCH p = (d)-[:BECAUSE_OF|DERIVED_FROM*1..%d]->(pr:Premise) "
        "OPTIONAL MATCH (e)-[r:SUPPORTS|CONTRADICTS]->(pr) "
        "WITH d, ends, pr, collect({rel: type(r), at: r.at, stated: r.stated, kind: e.kind}) AS ev "
        "RETURN d.id, d.decided_on, ends, pr.id, ev, pr.advisory ORDER BY d.id" % depth).result_set
    decisions: dict[str, dict] = {}
    for did, decided, ends, pid, ev, advisory in rows:
        item = decisions.setdefault(did, dict(decided_on=decided or "", ends=[x for x in ends if x.get("at")], premises={}))
        if pid:
            item["premises"][pid] = ([e for e in ev if e.get("at")], bool(advisory))
    y, m = int(start[:4]), int(start[5:7])
    points = []
    while True:
        # last day of month (y, m)
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        last = (date(ny, nm, 1) - date.resolution).isoformat()
        as_of = min(last, end)
        verdicts = {}
        for did, item in decisions.items():
            if item["decided_on"] > as_of:
                continue  # not decided yet as of that date
            states = [dict(state=premise_state([e for e in evs if _known(e, as_of)], adv)) for evs, adv in item["premises"].values()]
            verdicts[did] = decision_verdict(states, any(_known(x, as_of) for x in item["ends"]))
        counts: dict[str, int] = {}
        for v in verdicts.values():
            counts[v] = counts.get(v, 0) + 1
        points.append(dict(as_of=as_of, counts=counts, moot=sorted(d for d, v in verdicts.items() if v == "MOOT"),
                           disputed=sorted(d for d, v in verdicts.items() if v == "DISPUTED")))
        if as_of >= end:
            break
        y, m = ny, nm
    for i in range(1, len(points)):
        points[i]["newly_moot"] = sorted(set(points[i]["moot"]) - set(points[i - 1]["moot"]))
    points[0]["newly_moot"] = []
    return points


# Memory: findings written back after approval, and read before answering.
def findings(g: Graph, decision_id: str) -> list[dict]:
    rows = _q(g, 
        "MATCH (f:Finding)-[:ABOUT]->(d:Decision {id: $id}) OPTIONAL MATCH (f)-[:SUPERSEDED_BY]->(n:Finding) "
        "OPTIONAL MATCH (f)-[:ASSIGNED_TO]->(p:Person) "
        "RETURN f, n.id, p.name ORDER BY f.created_at DESC", {"id": decision_id}).result_set
    return [dict(_node(f), superseded_by=n, assignee=a) for f, n, a in rows]


def write_finding(g: Graph, decision_id: str, verdict: str, as_of: str, depth: int, cites: list[str], note: str = "",
                  kind: str = "verdict", assignee: str | None = None) -> dict:
    """Write an approved verdict (or re-open memo) as a Finding node. Called only after a human approves."""
    fid = f"finding:{decision_id}:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}"
    digest = decision_digest(g, decision_id)
    _q(g, 
        "MATCH (d:Decision {id: $did}) "
        "OPTIONAL MATCH (prev:Finding)-[:ABOUT]->(d) WHERE NOT (prev)-[:SUPERSEDED_BY]->() "
        "WITH d, collect(prev) AS prevs "
        "CREATE (f:Finding {id: $fid, verdict: $verdict, kind: $kind, as_of: $as_of, depth: $depth, note: $note, created_at: $now, valid_from: $as_of, digest: $digest}) "
        "CREATE (f)-[:ABOUT]->(d) "
        "WITH f, prevs UNWIND (CASE WHEN size(prevs) = 0 THEN [null] ELSE prevs END) AS p "
        "FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | CREATE (p)-[:SUPERSEDED_BY]->(f)) "
        "WITH DISTINCT f OPTIONAL MATCH (who:Person {id: $assignee}) "
        "FOREACH (_ IN CASE WHEN who IS NULL THEN [] ELSE [1] END | CREATE (f)-[:ASSIGNED_TO]->(who)) "
        "WITH f UNWIND $cites AS c MATCH (e:Evidence {id: c}) CREATE (f)-[:CITES]->(e)",
        {"did": decision_id, "fid": fid, "verdict": verdict, "kind": kind, "as_of": as_of, "depth": int(depth), "note": note,
         "now": datetime.now(timezone.utc).isoformat(timespec="seconds"), "cites": cites, "assignee": assignee, "digest": digest}, write=True)
    return dict(id=fid, decision_id=decision_id, verdict=verdict, kind=kind, as_of=as_of, depth=depth, cites=cites, assignee=assignee, digest=digest)


# Learning from rulings: when an owner rules on a premise the gate could not vouch for, the ruling is a dated
# SUPPORTS or CONTRADICTS edge from a Finding. The next audit reads it like any evidence and cites it, so the gate stops
# asking a question a human already settled, until newer evidence lands after the ruling (verdict.premise_state).
RULABLE = ("disputed", "unevidenced", "unchecked")


def write_ruling(g: Graph, decision_id: str, premise_id: str, holds: bool, as_of: str, by: str | None = None, note: str = "") -> dict:
    """Called only after a human approves. Refuses a premise outside the decision's audited subgraph, or one that needs no ruling."""
    a = audit_decision(g, decision_id, as_of, GATE_DEPTH)
    if not a["found"]:
        return dict(error=f"{decision_id} is not in the graph")
    p = next((x for x in a["premises"] if x["id"] == premise_id), None)
    if p is None:
        return dict(error=f"{premise_id} is not a reason behind {decision_id}")
    if p["state"] not in RULABLE:
        return dict(error=f"\"{p['text']}\" is {p['state']} on {as_of}; only a disputed, unchecked or unevidenced reason takes a ruling")
    rel = "SUPPORTS" if holds else "CONTRADICTS"
    fid = f"ruling:{premise_id}:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}"
    title = f"Owner ruling on {as_of}: still holds" if holds else f"Owner ruling on {as_of}: no longer holds"
    res = _q(g,
        "MATCH (d:Decision {id: $did}), (pr:Premise {id: $pid}) "
        "CREATE (f:Finding {id: $fid, kind: 'ruling', ruling: $ruling, title: $title, date: $as_of, as_of: $as_of, note: $note, "
        "created_at: $now, valid_from: $as_of, was: $was}) "
        "CREATE (f)-[:RULES_ON]->(d) CREATE (f)-[:%s {at: $as_of, quote: $note}]->(pr) "
        "WITH f OPTIONAL MATCH (who:Person {id: $by}) "
        "FOREACH (_ IN CASE WHEN who IS NULL THEN [] ELSE [1] END | CREATE (who)-[:AUTHORED]->(f)) RETURN f.id" % rel,
        {"did": decision_id, "pid": premise_id, "fid": fid, "ruling": "holds" if holds else "expired", "title": title, "as_of": as_of,
         "note": note, "now": datetime.now(timezone.utc).isoformat(timespec="seconds"), "was": p["state"], "by": by}, write=True).result_set
    if not res:
        return dict(error="nothing written")
    return dict(id=fid, decision_id=decision_id, premise_id=premise_id, rel=rel, at=as_of, was=p["state"], by=by,
                gate=check_action(g, decision_id, as_of)["gate"])


def rulings(g: Graph, decision_id: str) -> list[dict]:
    rows = _q(g, "MATCH (f:Finding {kind: 'ruling'})-[:RULES_ON]->(:Decision {id: $id}) MATCH (f)-[r:SUPPORTS|CONTRADICTS]->(pr:Premise) "
                 "OPTIONAL MATCH (a:Person)-[:AUTHORED]->(f) RETURN f, pr.id, type(r), a.name ORDER BY f.created_at", {"id": decision_id}).result_set
    return [dict(_node(f), premise=pid, rel=rel, by=who) for f, pid, rel, who in rows]


# The evidence packet: everything a reviewer needs to check one verdict without Moot, as JSON or Markdown.
SYNTHETIC_GRAPHS = {"larkspur"}


def is_synthetic(name: str) -> bool:
    return name in SYNTHETIC_GRAPHS or name.startswith("moot_")


def evidence_packet(g: Graph, decision_id: str, as_of: str | None = None) -> dict:
    as_of = as_of or today()
    a = audit_decision(g, decision_id, as_of, GATE_DEPTH)
    if not a["found"]:
        return dict(found=False, decision_id=decision_id)
    gt = check_action(g, decision_id, as_of)
    memo = reopen_memo(g, decision_id, as_of, GATE_DEPTH) if a["verdict"] in ("MOOT", "DISPUTED") else None
    receipts = [dict(premise=p["id"], text=p["text"], state=p["state"], hops=p["hops"], path=[n["id"] for n in p["path"]],
                     unchecked=p.get("unchecked"),
                     evidence=[{k: e.get(k) for k in ("id", "kind", "title", "rel", "at", "stated", "quote", "author") if e.get(k) is not None}
                               for e in p["evidence"]]) for p in a["premises"]]
    synthetic = is_synthetic(g.name)
    caveats = [c for c in (
        "Synthetic data: Larkspur is a fictional company; every document here was generated from a spec." if synthetic else None,
        "A verdict only covers reasons someone wrote down. A premise can stop being true without any document saying so.",
        "REVALIDATE is not a verdict on the decision: it means the graph cannot vouch for it." if gt["gate"] == "REVALIDATE" else None,
        "Evidence counts from the later of the date it took effect and the date it was stated, so nothing is used before it was knowable.",
    ) if c]
    return dict(found=True, decision=dict(id=a["decision"]["id"], title=a["decision"]["title"], decided_on=a["decision"].get("decided_on")),
                as_of=as_of, depth=GATE_DEPTH, verdict=a["verdict"], gate=gt["gate"], reasons=gt["reasons"], basis=gt["basis"],
                superseded_by=a.get("superseded_by"), owner=a.get("owner"), receipts=receipts, rulings=rulings(g, decision_id),
                findings=findings(g, decision_id), memo=memo["text"] if memo else None, synthetic=synthetic, caveats=caveats,
                snapshot=dict(gt["snapshot"], graph_digest=graph_digest(g)))


def packet_markdown(pk: dict) -> str:
    d, s = pk["decision"], pk["snapshot"]
    out = [f"# Evidence packet: {d['id']} {d['title']}", "",
           f"- Verdict as of {pk['as_of']}: **{pk['verdict']}** · agent gate: **{pk['gate']}** (depth {pk['depth']})",
           f"- Graph `{s['graph']}` · decision digest `{s['digest']}` · graph digest `{s['graph_digest']}`",
           f"- Decided on {d.get('decided_on')}" + (f" · owner {pk['owner']['name']}" + ("" if pk["owner"]["active"] else f" (left {pk['owner']['valid_to']})") if pk.get("owner") else "")]
    if pk["synthetic"]:
        out.append("- **Synthetic data**")
    if pk.get("superseded_by"):
        x = pk["superseded_by"]
        out.append(f"- Retired on {x['at']} by {x['id']} ({x['title']})")
    out += ["", "## Why the gate said " + pk["gate"], ""]
    out += [f"- `{r['code']}`: {r['text']}" for r in pk["reasons"]] or ["- every premise has dated support"]
    out += ["", "## Receipts", ""]
    for r in pk["receipts"]:
        out.append(f"- **{r['premise']}** \"{r['text']}\": {r['state']} ({r['hops']} hop{'s' if r['hops'] != 1 else ''}: {' → '.join(r['path'])})")
        if r.get("unchecked"):
            out.append(f"  - could not be checked: {r['unchecked']}")
        for e in r["evidence"]:
            when = e["at"] + (f", stated {e['stated']}" if e.get("stated") and e["stated"] != e["at"] else "")
            q = f" \"{e['quote']}\"" if e.get("quote") else ""
            out.append(f"  - {when} {e['rel']} by `{e['id']}` ({e.get('kind') or '?'}{', ' + e['author'] if e.get('author') else ''}): {e.get('title') or ''}.{q}")
        if not r["evidence"] and not r.get("unchecked"):
            out.append("  - no dated evidence either way")
    if pk["rulings"]:
        out += ["", "## Owner rulings", ""] + [f"- {x['as_of']} `{x['id']}` on {x['premise']}: {x['ruling']} (was {x['was']}){', by ' + x['by'] if x.get('by') else ''}. {x.get('note') or ''}".rstrip() for x in pk["rulings"]]
    if pk.get("memo"):
        out += ["", "## Re-open memo", "", "```", pk["memo"], "```"]
    out += ["", "## Caveats", ""] + [f"- {c}" for c in pk["caveats"]]
    out += ["", f"Re-check: `GET /api/gate/{d['id']}?as_of={pk['as_of']}` returns the same verdict while the decision digest is `{s['digest']}`."]
    return "\n".join(out) + "\n"


def schema(g: Graph) -> dict:
    labels = [r[0] for r in _q(g, "CALL db.labels()").result_set]
    rels = [r[0] for r in _q(g, "CALL db.relationshipTypes()").result_set]
    return dict(labels=labels, relationships=rels)


# 8. Orphaned decisions: the owner of record has left. Each one is routed up the reporting line,
#    as it stood on the day the owner left, to the first person who is still here.
def successor(g: Graph, person_id: str, left_on: str, as_of: str | None = None) -> dict | None:
    as_of = as_of or today()
    rows = _q(g,
        "MATCH (o:Person {id: $pid}) MATCH path = (o)-[:REPORTS_TO*1..5]->(m:Person) "
        "WHERE all(r IN relationships(path) WHERE r.valid_from <= $at AND (r.valid_to = '' OR r.valid_to > $at)) "
        "AND (m.left = '' OR m.left > $as_of) "
        "RETURN m.id, m.name, m.role, [n IN nodes(path) | {id: n.id, name: n.name, role: n.role, left: n.left}], length(path) "
        "ORDER BY length(path) LIMIT 1", {"pid": person_id, "at": left_on, "as_of": as_of}).result_set
    if not rows:
        return None
    mid, name, role, chain, hops = rows[0]
    return dict(id=mid, name=name, role=role, chain=chain, hops=hops)


def orphans(g: Graph, as_of: str | None = None, depth: int = 4) -> dict:
    """Every live decision whose owner of record has left, grouped by the person who left, with the suggested new owner."""
    as_of = as_of or today()
    owners = owners_as_of(g, as_of)
    live = {r["id"]: r for r in ledger(g, as_of, depth) if r["verdict"] != "RETIRED"}
    by_person: dict[str, dict] = {}
    for did, o in owners.items():
        if did not in live or o["active"]:
            continue
        grp = by_person.get(o["id"])
        if grp is None:
            grp = by_person[o["id"]] = dict(person=dict(id=o["id"], name=o["name"], role=o["role"], left=o["valid_to"]),
                                            successor=successor(g, o["id"], o["valid_to"], as_of), decisions=[])
        a = audit_decision(g, did, as_of, depth)
        grp["decisions"].append(dict(id=did, title=live[did]["title"], verdict=live[did]["verdict"], systems=live[did]["systems"],
                                     decided_on=live[did]["decided_on"],
                                     reasons=[dict(id=p["id"], text=p["text"], state=p["state"], hops=p["hops"]) for p in a["premises"]]))
    groups = sorted(by_person.values(), key=lambda x: x["person"]["left"] or "")
    return dict(as_of=as_of, groups=groups, count=sum(len(x["decisions"]) for x in groups))


def handover(g: Graph, decision_id: str, to_id: str, as_of: str) -> dict:
    """Approved handover: a new OWNS edge from `as_of`. The old edge keeps its dates, so time travel still shows who owned it then."""
    cur = decision_owner(g, decision_id, as_of)
    if cur and cur["id"] == to_id and cur["active"]:
        return dict(decision_id=decision_id, to=to_id, unchanged=True)
    res = _q(g,
        "MATCH (d:Decision {id: $did}), (p:Person {id: $to}) WHERE p.left = '' OR p.left > $as_of "
        "CREATE (p)-[:OWNS {valid_from: $as_of, valid_to: '', handed_over_from: $prev, approved_at: $now}]->(d) RETURN p.name",
        {"did": decision_id, "to": to_id, "as_of": as_of, "prev": cur["id"] if cur else "",
         "now": datetime.now(timezone.utc).isoformat(timespec="seconds")}, write=True).result_set
    if not res:
        return dict(decision_id=decision_id, to=to_id, error="no such decision, or that person is not active on that date")
    return dict(decision_id=decision_id, to=to_id, to_name=res[0][0], from_id=cur["id"] if cur else None, valid_from=as_of)


# 9. The re-open memo: which reason broke, the evidence that broke it, what else rests on it, who should own the follow-up.
def reopen_memo(g: Graph, decision_id: str, as_of: str | None = None, depth: int = 4) -> dict:
    as_of = as_of or today()
    a = audit_decision(g, decision_id, as_of, depth)
    if not a["found"]:
        return dict(found=False, decision_id=decision_id)
    d = a["decision"]
    verdicts = {r["id"]: r["verdict"] for r in ledger(g, as_of, depth)}
    broken, affected, cites = [], {}, []
    for p in a["premises"]:
        if p["state"] not in ("expired", "disputed"):
            continue
        ev = sorted(p["evidence"], key=lambda e: e["at"])
        contra = [e for e in ev if e["rel"] == "CONTRADICTS"][-1]
        reaffirm = next((e for e in reversed(ev) if e["rel"] == "SUPPORTS" and e["at"] >= contra["at"]), None)
        stated = p["path"][1] if len(p["path"]) > 1 else dict(id=p["id"], title=p["text"])
        broken.append(dict(premise=dict(id=p["id"], text=p["text"]), stated=dict(id=stated["id"], text=stated["title"]),
                           hops=p["hops"], state=p["state"], path=p["path"], evidence=contra, reaffirmed_by=reaffirm))
        cites.append(contra["id"])
        for x in premise_impact(g, p["id"])["decisions"]:
            if x["id"] != d["id"] and x["id"] in verdicts:
                affected.setdefault(x["id"], dict(id=x["id"], title=x["title"], verdict=verdicts[x["id"]], via=p["id"], hops=x["hops"]))
    owner = a.get("owner")
    if owner and owner["active"]:
        suggested = dict(id=owner["id"], name=owner["name"], role=owner.get("role"), why="current owner of record")
    elif owner:
        s = successor(g, owner["id"], owner["valid_to"], as_of)
        chain = " → ".join(n["name"] + (f" (left {n['left']})" if n.get("left") and n["left"] <= as_of else "") for n in (s["chain"] if s else []))
        suggested = (dict(id=s["id"], name=s["name"], role=s["role"], why=f"{owner['name']} left on {owner['valid_to']}; reporting line {chain}")
                     if s else dict(id=None, name=None, role=None, why=f"{owner['name']} left and no one in their reporting line is still here"))
    else:
        suggested = dict(id=None, name=None, role=None, why="no owner on record")
    memo = dict(found=True, decision=dict(id=d["id"], title=d["title"], decided_on=d["decided_on"]), verdict=a["verdict"], as_of=as_of,
                depth=a["depth"], broken=broken, affected=sorted(affected.values(), key=lambda x: x["id"]), owner=owner,
                suggested_owner=suggested, cites=cites)
    memo["text"] = memo_text(memo)
    return memo


def memo_text(m: dict) -> str:
    d = m["decision"]
    lines = [f"Re-open {d['id']}: {d['title']}", f"Moot verdict as of {m['as_of']}: {m['verdict']}", ""]
    if not m["broken"]:
        lines.append("No stated reason has broken. Nothing to re-open.")
        return "\n".join(lines)
    lines.append("Which reason broke")
    for b in m["broken"]:
        via = "" if b["hops"] == 1 else f" (the stated reason, \"{b['stated']['text']}\", only holds because of it)"
        lines.append(f"- \"{b['premise']['text']}\"{via}: {b['state']}.")
    lines += ["", "The new evidence"]
    for b in m["broken"]:
        e = b["evidence"]
        q = (e.get("quote") or "").strip()
        if q and not q.endswith((".", "!", "?")):
            q = q.rsplit(" ", 1)[0] + "…"
        lines.append(f"- {e['at']} {e['id']}: {e['title']}." + (f" Quote: \"{q}\"" if q else ""))
        if b["reaffirmed_by"]:
            r = b["reaffirmed_by"]
            lines.append(f"  Later re-affirmed on {r['at']} by {r['id']}: {r['title']}. Disputed, not dead.")
    lines += ["", "Other decisions resting on the same reason"]
    lines += [f"- {x['id']} {x['title']} ({x['verdict']})" for x in m["affected"]] or ["- none"]
    s = m["suggested_owner"]
    lines += ["", f"Suggested owner for the follow-up: {s['name'] or 'unassigned'} ({s['why']})"]
    return "\n".join(lines)


# 10. What if a reason broke tomorrow? Every decision that rests on it, directly or through derived premises, and what it would flip to.
def find_premise(g: Graph, query: str, limit: int = 5) -> list[dict]:
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in STOP | WHATIF_STOP and len(w) > 2]
    if not words:
        return []
    rows = _q(g,
        "CALL db.idx.fulltext.queryNodes('Premise', $q) YIELD node, score RETURN node.id, node.text, score ORDER BY score DESC LIMIT $limit",
        {"q": " | ".join(f"{w}*" for w in words), "limit": limit * 3}).result_set
    out = [dict(id=r[0], text=r[1], score=r[2], matched_terms=sum(1 for w in words if w in r[1].lower())) for r in rows]
    if out:  # on a tie, prefer the broader reason: the one more decisions rest on
        reach = dict(_q(g, "UNWIND $ids AS pid MATCH (pr:Premise {id: pid}) OPTIONAL MATCH (d:Decision)-[:BECAUSE_OF|DERIVED_FROM*1..6]->(pr) "
                           "RETURN pid, count(DISTINCT d)", {"ids": [c["id"] for c in out]}).result_set)
        for c in out:
            c["decisions"] = reach.get(c["id"], 0)
    return sorted(out, key=lambda c: (-c["matched_terms"], -c.get("decisions", 0), -c["score"]))[:limit]


WHATIF_STOP = set("what if happens happen were was would changes change stopped stops went goes longer anymore any more broke breaks".split())


def what_if(g: Graph, premise_id: str, as_of: str | None = None, depth: int = 4) -> dict:
    as_of = as_of or today()
    depth = max(1, min(int(depth), 6))
    pr = _q(g, "MATCH (pr:Premise {id: $id}) RETURN pr", {"id": premise_id}).result_set
    if not pr:
        return dict(found=False, premise_id=premise_id)
    rows = _q(g,
        "MATCH (pr:Premise {id: $id}) MATCH p = (d:Decision)-[:BECAUSE_OF|DERIVED_FROM*1..%d]->(pr) "
        "RETURN d.id, d.title, nodes(p), length(p) ORDER BY length(p)" % depth, {"id": premise_id}).result_set
    current = {r["id"]: r for r in ledger(g, as_of, depth)}
    seen, decisions = set(), []
    for did, title, path, hops in rows:
        if did in seen or did not in current:
            continue
        seen.add(did)
        before = current[did]["verdict"]
        after = before if before == "RETIRED" else "MOOT"
        decisions.append(dict(id=did, title=title, hops=hops, path=_path_ids(path), before=before, after=after,
                              flips=before != after, owner=current[did]["owner"], systems=current[did]["systems"]))
    decisions.sort(key=lambda x: (not x["flips"], x["hops"], x["id"]))
    return dict(found=True, premise=_node(pr[0][0]), as_of=as_of, depth=depth, decisions=decisions,
                would_fall=sum(1 for x in decisions if x["flips"]), already_moot=sum(1 for x in decisions if x["before"] == "MOOT"),
                systems=sorted({s for x in decisions for s in x["systems"]}))


# 11. The riskiest reasons: premises ranked by how many standing decisions sit below them.
def riskiest_reasons(g: Graph, as_of: str | None = None, depth: int = 4, limit: int = 10) -> dict:
    as_of = as_of or today()
    depth = max(1, min(int(depth), 6))
    current = {r["id"]: r for r in ledger(g, as_of, depth)}
    rows = _q(g,
        "MATCH (pr:Premise) OPTIONAL MATCH (d:Decision)-[:BECAUSE_OF|DERIVED_FROM*1..%d]->(pr) "
        "OPTIONAL MATCH (e)-[r:SUPPORTS|CONTRADICTS]->(pr) WHERE %s "
        "RETURN pr.id, pr.text, pr.kind, collect(DISTINCT d.id), collect(DISTINCT {rel: type(r), at: r.at, stated: r.stated, kind: e.kind}), pr.advisory" % (depth, KNOWN),
        {"as_of": as_of}).result_set
    rank = {r[0]: r[1] for r in _q(g, "CALL algo.pageRank(null, null) YIELD node, score WHERE node:Premise RETURN node.id, score").result_set}
    out = []
    for pid, text, kind, dids, ev, advisory in rows:
        live = [current[x] for x in dids if x in current and current[x]["verdict"] != "RETIRED"]
        if not live:
            continue
        standing = [x for x in live if x["verdict"] != "MOOT"]
        out.append(dict(id=pid, text=text, kind=kind, state=premise_state([e for e in ev if e.get("at")], bool(advisory)),
                        decisions=len(live), standing=len(standing), decision_ids=sorted(x["id"] for x in live),
                        systems=sorted({s for x in live for s in x["systems"]}), pagerank=rank.get(pid)))
    out.sort(key=lambda x: (-x["standing"], -x["decisions"], x["id"]))
    pr_order = sorted(out, key=lambda x: -(x["pagerank"] or 0))
    for i, x in enumerate(out):
        x["rank"] = i + 1
        x["pagerank_rank"] = pr_order.index(x) + 1
    return dict(as_of=as_of, depth=depth, reasons=out[:limit], total=len(out))
