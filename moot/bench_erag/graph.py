"""The blind supersession graph in FalkorDB (graph `erag`), and the one query the cut is decided by.

  (:Question {id})-[:RETRIEVED {rank}]->(:Doc {id})
  (:Doc)-[:SUPERSEDES {qid, old, new, span, evidence, rule}]->(:Doc)

Written only from pools.json (question text -> BM25 ranking) and extract.edges (document text). The answer key
never reaches this graph.
"""
from __future__ import annotations

from moot.graph import connect

GRAPH = "erag"

CUT_QUERY = (
    "MATCH (q:Question {id: $qid})-[r:RETRIEVED]->(old:Doc)<-[s:SUPERSEDES]-(new:Doc)<-[:RETRIEVED]-(q) "
    "WHERE s.qid = $qid "
    "RETURN old.id, r.rank, new.id, s.old, s.new, s.span, s.evidence, s.rule ORDER BY r.rank"
)


def handle(name: str = GRAPH):
    return connect().select_graph(name)


def write(pools: dict[str, dict], edges: dict[str, list], name: str = GRAPH) -> dict:
    g = handle(name)
    try:
        g.delete()
    except Exception:
        pass
    g.query("CREATE INDEX FOR (d:Doc) ON (d.id)")
    g.query("CREATE INDEX FOR (q:Question) ON (q.id)")
    docs = sorted({d for p in pools.values() for d in p["ranking"]})
    for i in range(0, len(docs), 5000):
        g.query("UNWIND $ids AS id MERGE (:Doc {id: id})", {"ids": docs[i:i + 5000]})
    qs = [dict(id=q, text=p["question"]) for q, p in pools.items()]
    g.query("UNWIND $qs AS q MERGE (n:Question {id: q.id}) SET n.text = q.text", {"qs": qs})
    ret = [dict(q=q, d=d, rank=i + 1) for q, p in pools.items() for i, d in enumerate(p["ranking"])]
    for i in range(0, len(ret), 5000):
        g.query("UNWIND $rows AS r MATCH (q:Question {id: r.q}), (d:Doc {id: r.d}) CREATE (q)-[:RETRIEVED {rank: r.rank}]->(d)",
                {"rows": ret[i:i + 5000]})
    sup = [dict(qid=q, src=e["new_doc"], dst=e["old_doc"], old=e["old"], new=e["new"], span=e["span"],
                evidence=e["evidence"], rule=e["rule"]) for q, es in edges.items() for e in es]
    for i in range(0, len(sup), 2000):
        g.query("UNWIND $rows AS r MATCH (a:Doc {id: r.src}), (b:Doc {id: r.dst}) "
                "CREATE (a)-[:SUPERSEDES {qid: r.qid, old: r.old, new: r.new, span: r.span, evidence: r.evidence, rule: r.rule}]->(b)",
                {"rows": sup[i:i + 2000]})
    return dict(docs=len(docs), questions=len(qs), retrieved=len(ret), supersedes=len(sup))


def superseded(qid: str, name: str = GRAPH) -> list[dict]:
    rows = handle(name).ro_query(CUT_QUERY, {"qid": qid}).result_set
    keys = ("old_doc", "rank", "new_doc", "old", "new", "span", "evidence", "rule")
    return [dict(zip(keys, r)) for r in rows]
