"""The map view's data: the whole decision network and how each verdict and reason state moved month by month.
Read-only. Every row comes from a FalkorDB read query or the existing audit tools, so the map draws the real graph."""
from __future__ import annotations

from datetime import date

from falkordb import Graph

from . import tools

QUERIES = {
    "nodes": "MATCH (n) WHERE n:Decision OR n:Premise OR n:System OR n:Person RETURN labels(n)[0], properties(n)",
    "evidence": "MATCH (e:Evidence)-[r:CONTRADICTS|SUPPORTS]->(p:Premise) "
                "OPTIONAL MATCH (a:Person)-[:AUTHORED]->(e) "
                "RETURN DISTINCT properties(e), a.id",
    "edges": "MATCH (a)-[r]->(b) WHERE type(r) IN ['BECAUSE_OF','DERIVED_FROM','CONTRADICTS','SUPPORTS','GOVERNS','OWNS',"
             "'REPORTS_TO','SUPERSEDES','RETIRES'] RETURN a.id, type(r), b.id, properties(r)",
    "pagerank": "CALL algo.pageRank(null, null) YIELD node, score WHERE node:Premise RETURN node.id, score",
    "islands": "CALL algo.WCC({nodeLabels:['Decision','Premise'], relationshipTypes:['BECAUSE_OF','DERIVED_FROM','SUPERSEDES']}) "
               "YIELD node, componentId RETURN node.id, componentId",
}


def month_ends(end: str, start: str = "2025-01-01") -> list[str]:
    """The last day of every month from `start` to `end`, with `end` itself as the final point (as the rot chart does)."""
    out, y, m = [], int(start[:4]), int(start[5:7])
    while True:
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        last = min((date(ny, nm, 1) - date.resolution).isoformat(), end)
        out.append(last)
        if last >= end:
            return out
        y, m = ny, nm


def export(g: Graph, as_of: str | None = None, depth: int = 4) -> dict:
    end = as_of or tools.today()
    depth = max(1, min(int(depth), 6))
    nodes = [dict(label=label, **props) for label, props in tools._q(g, QUERIES["nodes"]).result_set]
    for props, author in tools._q(g, QUERIES["evidence"]).result_set:
        nodes.append(dict(label="Evidence", author=author, **{k: v for k, v in props.items() if k != "embedding"}))
    edges = [dict(src=a, rel=t, dst=b, **(p or {})) for a, t, b, p in tools._q(g, QUERIES["edges"]).result_set]
    pagerank = {i: s for i, s in tools._q(g, QUERIES["pagerank"]).result_set}
    islands = {i: c for i, c in tools._q(g, QUERIES["islands"]).result_set}

    months = month_ends(end)
    ids = [n["id"] for n in nodes if n["label"] == "Decision"]
    verdicts: dict[str, list] = {d: [None] * len(months) for d in ids}   # None before the decision was made
    premise_state: dict[str, list] = {}                                   # None while no decision rests on it
    for i, m in enumerate(months):
        for row in tools.ledger(g, m, depth):
            verdicts[row["id"]][i] = row["verdict"]
        for d in ids:
            if verdicts[d][i] is None:
                continue
            for p in tools.audit_decision(g, d, m, depth)["premises"]:
                premise_state.setdefault(p["id"], [None] * len(months))[i] = p["state"]

    final = {d: tools.audit_decision(g, d, end, depth) for d in ids}
    gates = {d: tools.check_action(g, d, end) for d in ids}
    return dict(
        tenant=g.name, as_of=end, depth=depth, months=months, nodes=nodes, edges=edges, pagerank=pagerank, islands=islands,
        verdicts=verdicts, premise_state=premise_state,
        gate={d: dict(action=v["gate"], reasons=v.get("reasons", [])[:3]) for d, v in gates.items()},
        owners=tools.owners_as_of(g, end),
        paths={d: [dict(id=p["id"], hops=p["hops"], state=p["state"], path=[x["id"] for x in p["path"]]) for p in a["premises"]]
               for d, a in final.items()},
        queries=QUERIES,
    )
