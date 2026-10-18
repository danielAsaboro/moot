"""Post a change: try a new piece of evidence against a company's decisions without touching the company's graph.

  create(g, change)   copy the company graph into a scratch graph `sandbox_<id>` (rows read and re-created, so it works on any
                      FalkorDB, including the embedded one whose GRAPH.COPY fork can deadlock), then add one dated Evidence node
                      and its SUPPORTS or CONTRADICTS edge on the premise the visitor picked. Every read tool then works on it
                      with ?graph=sandbox_<id>: the ledger, the gate, what-if, the timeline.
  diff(g, s, as_of)   which decisions changed verdict or gate between the company graph and the sandbox.
  delete(name)        Reset. Sandboxes also expire after an hour, and at most MAX live at once (the oldest goes first).

The company graph is only ever read. The change is written to the sandbox, which is the visitor's, and only there.
"""
from __future__ import annotations

import re
import time
import uuid

from falkordb import Graph

from . import tools
from .graph import connect, ensure_schema

PREFIX = "sandbox_"
MAX = 20
TTL = 3600


def _all(g: Graph):
    nodes = tools._q(g, "MATCH (n) RETURN labels(n)[0], properties(n)").result_set
    edges = tools._q(g, "MATCH (a)-[r]->(b) RETURN labels(a)[0], a.id, type(r), labels(b)[0], b.id, properties(r)").result_set
    return nodes, edges


def sweep() -> None:
    db = connect()
    names = sorted((n for n in db.list_graphs() if n.startswith(PREFIX)), key=lambda n: int(n.split("_")[1]))
    now = int(time.time())
    for i, n in enumerate(names):
        if now - int(n.split("_")[1]) > TTL or i < len(names) - MAX + 1:
            try:
                db.select_graph(n).delete()
            except Exception:
                pass


def create(g: Graph, premise_id: str, rel: str, at: str, title: str) -> dict:
    if rel not in ("SUPPORTS", "CONTRADICTS"):
        raise ValueError("rel must be SUPPORTS or CONTRADICTS")
    if not tools._q(g, "MATCH (p:Premise {id: $id}) RETURN p.id", {"id": premise_id}).result_set:
        raise ValueError(f"no reason {premise_id} in graph {g.name}")
    sweep()
    name = f"{PREFIX}{int(time.time())}_{uuid.uuid4().hex[:8]}"
    s = connect().select_graph(name)
    nodes, edges = _all(g)
    ensure_schema(s)
    by_label: dict[str, list] = {}
    for label, props in nodes:
        by_label.setdefault(label, []).append(props)
    for label, rows in by_label.items():
        tools._q(s, f"UNWIND $rows AS row CREATE (n:{label}) SET n = row", {"rows": rows}, write=True)
    by_rel: dict[tuple, list] = {}
    for la, a, r, lb, b, props in edges:
        by_rel.setdefault((la, r, lb), []).append(dict(a=a, b=b, p=props))
    for (la, r, lb), rows in by_rel.items():
        tools._q(s, f"UNWIND $rows AS row MATCH (a:{la} {{id: row.a}}), (b:{lb} {{id: row.b}}) CREATE (a)-[r:{r}]->(b) SET r = row.p",
                 {"rows": rows}, write=True)
    eid = f"posted:{uuid.uuid4().hex[:6]}"
    tools._q(s, "MATCH (p:Premise {id: $pid}) CREATE (e:Evidence {id: $eid, kind: 'posted', title: $title, date: $at, excerpt: $title}) "
                f"CREATE (e)-[:{rel} {{at: $at, quote: $title}}]->(p)",
             {"pid": premise_id, "eid": eid, "title": re.sub(r"\s+", " ", title)[:200], "at": at}, write=True)
    return dict(sandbox=name, evidence=eid, premise=premise_id, rel=rel, at=at, base=g.name, expires_in=TTL)


def diff(g: Graph, s: Graph, as_of: str, depth: int = 4) -> list[dict]:
    before = {r["id"]: r for r in tools.ledger(g, as_of, depth)}
    after = {r["id"]: r for r in tools.ledger(s, as_of, depth)}
    out = []
    for did, a in after.items():
        b = before.get(did)
        if b and b["verdict"] != a["verdict"]:
            out.append(dict(id=did, title=a["title"], before=b["verdict"], after=a["verdict"],
                            gate_before=tools.check_action(g, did, as_of)["gate"], gate_after=tools.check_action(s, did, as_of)["gate"]))
    return sorted(out, key=lambda x: x["id"])


def delete(name: str) -> bool:
    if not name.startswith(PREFIX):
        return False
    try:
        connect().select_graph(name).delete()
        return True
    except Exception:
        return False
