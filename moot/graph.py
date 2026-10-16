"""FalkorDB connection, schema and idempotent seed.

One named graph per company (tenant). All reads in the product go through ro_query;
the only writes are the seed and Finding nodes written after a human approves.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from falkordb import FalkorDB, Graph

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

FULLTEXT = [("Decision", ("title", "summary")), ("Premise", ("text",)), ("Evidence", ("title", "excerpt"))]
RANGE = [("Decision", "id"), ("Premise", "id"), ("Evidence", "id"), ("Person", "id"), ("System", "id"), ("Finding", "id")]


def connect() -> FalkorDB:
    return FalkorDB(host=os.getenv("FALKORDB_HOST", "localhost"), port=int(os.getenv("FALKORDB_PORT", "6379")),
                    password=os.getenv("FALKORDB_PASSWORD") or None)


def tenant() -> str:
    return os.getenv("MOOT_TENANT", "larkspur")


def graph(name: str | None = None) -> Graph:
    return connect().select_graph(name or tenant())


def ensure_schema(g: Graph) -> None:
    for label, prop in RANGE:
        try:
            g.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
        except Exception as ex:  # already exists
            if "already indexed" not in str(ex).lower():
                raise
    for label, props in FULLTEXT:
        try:
            g.query(f"CALL db.idx.fulltext.createNodeIndex('{label}', {', '.join(repr(p) for p in props)})")
        except Exception as ex:
            if "already indexed" not in str(ex).lower():
                raise


def seed(g: Graph, graph_json: Path | None = None, fresh: bool = False) -> dict:
    """MERGE every node and edge from graph.json. Running it twice changes nothing.

    fresh=True drops the graph first (demo reset); it is the only destructive operation in the codebase.
    """
    if fresh:
        try:
            g.delete()
        except Exception:
            pass
    payload = json.loads((graph_json or DATA / "graph.json").read_text())
    ensure_schema(g)
    by_label: dict[str, list] = {}
    for n in payload["nodes"]:
        by_label.setdefault(n["label"], []).append(dict(id=n["id"], **n["props"]))
    for label, rows in by_label.items():
        keys = sorted({k for r in rows for k in r} - {"id"})
        sets = ", ".join(f"n.{k} = row.{k}" for k in keys)
        g.query(f"UNWIND $rows AS row MERGE (n:{label} {{id: row.id}})" + (f" SET {sets}" if sets else ""), {"rows": rows})
    # Edges are grouped by (source label, relationship, target label) so the MATCH on each end
    # hits the per-label id index. An unlabelled MATCH (a {id: ...}) cannot use it and scans.
    label_of = {n["id"]: n["label"] for n in payload["nodes"]}
    by_rel: dict[tuple, list] = {}
    for e in payload["edges"]:
        key = (label_of.get(e["src"], ""), e["rel"], label_of.get(e["dst"], ""))
        by_rel.setdefault(key, []).append(dict(src=e["src"], dst=e["dst"], **e["props"]))
    for (sl, rel, dl), rows in by_rel.items():
        keys = sorted({k for r in rows for k in r} - {"src", "dst"})
        sets = ", ".join(f"r.{k} = row.{k}" for k in keys)
        sl = f":{sl}" if sl else ""
        dl = f":{dl}" if dl else ""
        g.query(f"UNWIND $rows AS row MATCH (a{sl} {{id: row.src}}), (b{dl} {{id: row.dst}}) MERGE (a)-[r:{rel}]->(b)"
                + (f" SET {sets}" if sets else ""), {"rows": rows})
    return stats(g)


def stats(g: Graph) -> dict:
    nodes = g.ro_query("MATCH (n) RETURN labels(n)[0] AS l, count(n) AS c ORDER BY l").result_set
    rels = g.ro_query("MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS c ORDER BY t").result_set
    return dict(nodes={l: c for l, c in nodes}, edges={t: c for t, c in rels})
