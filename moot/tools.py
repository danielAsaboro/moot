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


# 6. The ledger: every decision with its verdict, in one pass.
def ledger(g: Graph, as_of: str | None = None, depth: int = 4) -> list[dict]:
    as_of = as_of or today()
    depth = max(1, min(int(depth), 6))
    rows = _q(g, 
        "MATCH (d:Decision) OPTIONAL MATCH (n:Decision)-[:SUPERSEDES]->(d) "
        "OPTIONAL MATCH p = (d)-[:BECAUSE_OF|DERIVED_FROM*1..%d]->(pr:Premise) "
        "OPTIONAL MATCH (e:Evidence)-[r:SUPPORTS|CONTRADICTS]->(pr) WHERE r.at <= $as_of "
        "WITH d, n, pr, collect({rel: type(r), at: r.at}) AS ev "
        "OPTIONAL MATCH (d)-[:GOVERNS]->(s:System) "
        "RETURN d, n.id, pr.id, ev, collect(DISTINCT s.name) ORDER BY d.id" % depth,
        {"as_of": as_of}).result_set
    owners = owners_as_of(g, as_of)
    out: dict[str, dict] = {}
    for d, sup, pid, ev, systems in rows:
        did = d.properties["id"]
        if d.properties.get("decided_on", "") > as_of:
            continue  # not decided yet as of that date
        o = owners.get(did)
        item = out.setdefault(did, dict(_node(d), superseded=bool(sup), premises={}, owner=o["name"] if o else None,
                                        owner_id=o["id"] if o else None, owner_active=bool(o and o["active"]), systems=systems))
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
        "OPTIONAL MATCH (f)-[:ASSIGNED_TO]->(p:Person) "
        "RETURN f, n.id, p.name ORDER BY f.created_at DESC", {"id": decision_id}).result_set
    return [dict(_node(f), superseded_by=n, assignee=a) for f, n, a in rows]


def write_finding(g: Graph, decision_id: str, verdict: str, as_of: str, depth: int, cites: list[str], note: str = "",
                  kind: str = "verdict", assignee: str | None = None) -> dict:
    """Write an approved verdict (or re-open memo) as a Finding node. Called only after a human approves."""
    fid = f"finding:{decision_id}:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}"
    _q(g, 
        "MATCH (d:Decision {id: $did}) "
        "OPTIONAL MATCH (prev:Finding)-[:ABOUT]->(d) WHERE NOT (prev)-[:SUPERSEDED_BY]->() "
        "WITH d, collect(prev) AS prevs "
        "CREATE (f:Finding {id: $fid, verdict: $verdict, kind: $kind, as_of: $as_of, depth: $depth, note: $note, created_at: $now, valid_from: $as_of}) "
        "CREATE (f)-[:ABOUT]->(d) "
        "WITH f, prevs UNWIND (CASE WHEN size(prevs) = 0 THEN [null] ELSE prevs END) AS p "
        "FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | CREATE (p)-[:SUPERSEDED_BY]->(f)) "
        "WITH DISTINCT f OPTIONAL MATCH (who:Person {id: $assignee}) "
        "FOREACH (_ IN CASE WHEN who IS NULL THEN [] ELSE [1] END | CREATE (f)-[:ASSIGNED_TO]->(who)) "
        "WITH f UNWIND $cites AS c MATCH (e:Evidence {id: c}) CREATE (f)-[:CITES]->(e)",
        {"did": decision_id, "fid": fid, "verdict": verdict, "kind": kind, "as_of": as_of, "depth": int(depth), "note": note,
         "now": datetime.now(timezone.utc).isoformat(timespec="seconds"), "cites": cites, "assignee": assignee}, write=True)
    return dict(id=fid, decision_id=decision_id, verdict=verdict, kind=kind, as_of=as_of, depth=depth, cites=cites, assignee=assignee)


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
        "OPTIONAL MATCH (e:Evidence)-[r:SUPPORTS|CONTRADICTS]->(pr) WHERE r.at <= $as_of "
        "RETURN pr.id, pr.text, pr.kind, collect(DISTINCT d.id), collect(DISTINCT {rel: type(r), at: r.at})" % depth,
        {"as_of": as_of}).result_set
    rank = {r[0]: r[1] for r in _q(g, "CALL algo.pageRank(null, null) YIELD node, score WHERE node:Premise RETURN node.id, score").result_set}
    out = []
    for pid, text, kind, dids, ev in rows:
        live = [current[x] for x in dids if x in current and current[x]["verdict"] != "RETIRED"]
        if not live:
            continue
        standing = [x for x in live if x["verdict"] != "MOOT"]
        out.append(dict(id=pid, text=text, kind=kind, state=premise_state([e for e in ev if e.get("at")]),
                        decisions=len(live), standing=len(standing), decision_ids=sorted(x["id"] for x in live),
                        systems=sorted({s for x in live for s in x["systems"]}), pagerank=rank.get(pid)))
    out.sort(key=lambda x: (-x["standing"], -x["decisions"], x["id"]))
    pr_order = sorted(out, key=lambda x: -(x["pagerank"] or 0))
    for i, x in enumerate(out):
        x["rank"] = i + 1
        x["pagerank_rank"] = pr_order.index(x) + 1
    return dict(as_of=as_of, depth=depth, reasons=out[:limit], total=len(out))
