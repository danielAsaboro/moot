"""The fixed catalogue of read-only graph tools.

Every tool is a parameterised Cypher query run with ro_query. The language model never
writes Cypher and never sees the database. Tools return plain dicts that the API, the MCP
server and the agent all share. Paths are returned as node lists so the UI can show them.
"""
from __future__ import annotations

import re
import time
from contextvars import ContextVar
from datetime import date, datetime, timezone

from falkordb import Graph

from .verdict import decision_verdict, premise_state

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
                       write=write))
    return res


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
    head = _q(g, 
        "MATCH (d:Decision {id: $id}) OPTIONAL MATCH (n:Decision)-[:SUPERSEDES]->(d) "
        "OPTIONAL MATCH (d)-[:RECORDED_IN]->(src:Evidence) OPTIONAL MATCH (d)-[:GOVERNS]->(s:System) "
        "RETURN d, n.id, n.title, src, collect(DISTINCT s.name)", {"id": decision_id}).result_set
    if not head:
        return dict(found=False, decision_id=decision_id, verdict="NOT_IN_GRAPH")
    d, sup_id, sup_title, src, systems = head[0]
    if d.properties.get("decided_on", "") > as_of:
        return dict(found=True, decision=_node(d), as_of=as_of, depth=depth, verdict="NOT_YET", premises=[], superseded_by=None,
                    source=(_node(src) if src else None), systems=systems, owner=decision_owner(g, decision_id, as_of))
    rows = _q(g, 
        "MATCH (d:Decision {id: $id}) MATCH p = (d)-[:BECAUSE_OF|DERIVED_FROM*1..%d]->(pr:Premise) "
        "OPTIONAL MATCH (e:Evidence)-[r:SUPPORTS|CONTRADICTS]->(pr) WHERE r.at <= $as_of "
        "RETURN pr, nodes(p) AS pn, length(p) AS hops, collect({id: e.id, title: e.title, kind: e.kind, date: e.date, rel: type(r), at: r.at, quote: r.quote}) "
        "ORDER BY hops" % depth, {"id": decision_id, "as_of": as_of}).result_set
    premises, seen = [], set()
    for pr, path_nodes, _hops, events in rows:
        pid = pr.properties["id"]
        if pid in seen:
            continue
        seen.add(pid)
        events = [e for e in events if e.get("id")]
        state = premise_state(events)
        premises.append(dict(id=pid, text=pr.properties["text"], kind=pr.properties.get("kind"), hops=len(path_nodes) - 1,
                             path=_path_ids(path_nodes), state=state,
                             evidence=sorted(events, key=lambda e: e["at"]),
                             contradicted_before_decision=any(e["rel"] == "CONTRADICTS" and e["at"] < d.properties["decided_on"] for e in events)))
    verdict = decision_verdict(premises, superseded=bool(sup_id))
    return dict(found=True, decision=_node(d), as_of=as_of, depth=depth, verdict=verdict, premises=premises,
                superseded_by=(dict(id=sup_id, title=sup_title) if sup_id else None),
                source=(_node(src) if src else None), systems=systems, owner=decision_owner(g, decision_id, as_of))


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


# 5. Who owns it, as of a date. Ownership edges carry validity windows.
def decision_owner(g: Graph, decision_id: str, as_of: str | None = None) -> dict | None:
    as_of = as_of or today()
    rows = _q(g, 
        "MATCH (p:Person)-[o:OWNS]->(d:Decision {id: $id}) RETURN p.id, p.name, p.role, o.valid_from, o.valid_to",
        {"id": decision_id}).result_set
    if not rows:
        return None
    pid, name, role, vf, vt = rows[0]
    active = (not vt) or vt >= as_of
    return dict(id=pid, name=name, role=role, valid_from=vf, valid_to=vt or None, active=active)


# 6. The ledger: every decision with its verdict, in one pass.
def ledger(g: Graph, as_of: str | None = None, depth: int = 4) -> list[dict]:
    as_of = as_of or today()
    depth = max(1, min(int(depth), 6))
    rows = _q(g, 
        "MATCH (d:Decision) OPTIONAL MATCH (n:Decision)-[:SUPERSEDES]->(d) "
        "OPTIONAL MATCH p = (d)-[:BECAUSE_OF|DERIVED_FROM*1..%d]->(pr:Premise) "
        "OPTIONAL MATCH (e:Evidence)-[r:SUPPORTS|CONTRADICTS]->(pr) WHERE r.at <= $as_of "
        "WITH d, n, pr, collect({rel: type(r), at: r.at}) AS ev "
        "OPTIONAL MATCH (o:Person)-[w:OWNS]->(d) OPTIONAL MATCH (d)-[:GOVERNS]->(s:System) "
        "RETURN d, n.id, pr.id, ev, o.name, w.valid_to, collect(DISTINCT s.name) ORDER BY d.id" % depth,
        {"as_of": as_of}).result_set
    out: dict[str, dict] = {}
    for d, sup, pid, ev, owner, left, systems in rows:
        did = d.properties["id"]
        if d.properties.get("decided_on", "") > as_of:
            continue  # not decided yet as of that date
        item = out.setdefault(did, dict(_node(d), superseded=bool(sup), premises={}, owner=owner,
                                        owner_active=(not left) or left >= as_of, systems=systems))
        if pid:
            item["premises"][pid] = premise_state([e for e in ev if e.get("at")])
    result = []
    for item in out.values():
        states = [dict(state=s) for s in item.pop("premises").values()]
        item["verdict"] = decision_verdict(states, item.pop("superseded"))
        item["expired_premises"] = sum(1 for s in states if s["state"] == "expired")
        result.append(item)
    order = {"MOOT": 0, "DISPUTED": 1, "UNDOCUMENTED": 2, "HOLDS": 3, "RETIRED": 4}
    return sorted(result, key=lambda r: (order[r["verdict"]], r["id"]))


# 7. The rot curve: the ledger re-run at month ends, so the UI can show verdicts drifting over time.
def timeline(g: Graph, start: str = "2025-01-01", end: str | None = None, depth: int = 4) -> list[dict]:
    end = end or today()
    y, m = int(start[:4]), int(start[5:7])
    points = []
    while True:
        # last day of month (y, m)
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        last = (date(ny, nm, 1) - date.resolution).isoformat()
        as_of = min(last, end)
        rows = ledger(g, as_of, depth)
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        points.append(dict(as_of=as_of, counts=counts, moot=[r["id"] for r in rows if r["verdict"] == "MOOT"],
                           disputed=[r["id"] for r in rows if r["verdict"] == "DISPUTED"]))
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
        "RETURN f, n.id ORDER BY f.created_at DESC", {"id": decision_id}).result_set
    return [dict(_node(f), superseded_by=n) for f, n in rows]


def write_finding(g: Graph, decision_id: str, verdict: str, as_of: str, depth: int, cites: list[str], note: str = "") -> dict:
    """The one write. Called only after a human approves in the UI or the MCP client."""
    fid = f"finding:{decision_id}:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}"
    _q(g, 
        "MATCH (d:Decision {id: $did}) "
        "OPTIONAL MATCH (prev:Finding)-[:ABOUT]->(d) WHERE NOT (prev)-[:SUPERSEDED_BY]->() "
        "WITH d, collect(prev) AS prevs "
        "CREATE (f:Finding {id: $fid, verdict: $verdict, as_of: $as_of, depth: $depth, note: $note, created_at: $now, valid_from: $as_of}) "
        "CREATE (f)-[:ABOUT]->(d) "
        "WITH f, prevs UNWIND (CASE WHEN size(prevs) = 0 THEN [null] ELSE prevs END) AS p "
        "FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | CREATE (p)-[:SUPERSEDED_BY]->(f)) "
        "WITH f UNWIND $cites AS c MATCH (e:Evidence {id: c}) CREATE (f)-[:CITES]->(e)",
        {"did": decision_id, "fid": fid, "verdict": verdict, "as_of": as_of, "depth": int(depth), "note": note,
         "now": datetime.now(timezone.utc).isoformat(timespec="seconds"), "cites": cites}, write=True)
    return dict(id=fid, decision_id=decision_id, verdict=verdict, as_of=as_of, depth=depth, cites=cites)


def schema(g: Graph) -> dict:
    labels = [r[0] for r in _q(g, "CALL db.labels()").result_set]
    rels = [r[0] for r in _q(g, "CALL db.relationshipTypes()").result_set]
    return dict(labels=labels, relationships=rels)
