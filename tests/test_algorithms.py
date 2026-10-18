"""Every graph algorithm Moot reports, cross-checked against NetworkX on the same rows, and shown to be load-bearing: change
the graph and the answer changes. Integration: needs FalkorDB, skipped when none is reachable."""
import networkx as nx
import pytest

from moot import people, tools
from moot.corpus import spec
from moot.graph import connect, seed

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def g():
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    graph = db.select_graph("moot_test_algorithms")
    seed(graph, fresh=True)
    yield graph
    graph.delete()


def knows_graph(c) -> nx.Graph:
    G = nx.Graph()
    G.add_nodes_from(r[0] for r in c.ro_query("MATCH (n) RETURN n.id").result_set)
    G.add_edges_from((p, d) for p, d in c.ro_query("MATCH (p:Person)-[:KNOWS]->(d:Decision) RETURN p.id, d.id").result_set)
    return G


def test_wcc_matches_networkx(g):
    with people.knowledge_copy(g, spec.AS_OF) as c:
        ours = sorted(sorted(i["decisions"] + i["people"]) for i in people.islands(c))
        theirs = sorted(sorted(cc) for cc in nx.connected_components(knows_graph(c)))
    assert ours == theirs


def test_betweenness_ranks_people_like_networkx(g):
    """Moot reports people ranked by betweenness. FalkorDB's scores are not Brandes' exact values on this projection (they are
    not a constant multiple of NetworkX's), so the claim checked is the one the product makes: the people come out in the
    same order."""
    with people.knowledge_copy(g, spec.AS_OF) as c:
        ours = dict(c.ro_query("CALL algo.betweenness({nodeLabels: ['Person','Decision'], relationshipTypes: ['KNOWS','KNOWN_BY'], "
                               "samplingSize: 10000, samplingSeed: 7}) YIELD node, score WHERE node:Person RETURN node.id, score").result_set)
        theirs = nx.betweenness_centrality(knows_graph(c), normalized=False)
    rank = lambda s: [k for k, _ in sorted(((k, v) for k, v in s.items() if k in ours), key=lambda kv: (-round(kv[1], 6), kv[0]))]
    assert rank(ours) == rank(theirs)


def test_pagerank_ranks_premises_like_networkx(g):
    ours = dict(g.ro_query("CALL algo.pageRank(null, null) YIELD node, score WHERE node:Premise RETURN node.id, score").result_set)
    D = nx.DiGraph()
    D.add_nodes_from(r[0] for r in g.ro_query("MATCH (n) RETURN n.id").result_set)
    D.add_edges_from((a, b) for a, b in g.ro_query("MATCH (a)-[]->(b) RETURN a.id, b.id").result_set)
    theirs = {k: v for k, v in nx.pagerank(D, alpha=0.85).items() if k in ours}
    top = lambda s: [k for k, _ in sorted(s.items(), key=lambda kv: (-round(kv[1], 6), kv[0]))][:5]
    assert set(top(ours)) == set(top(theirs))


def test_sppaths_lengths_match_networkx(g):
    rels = ("CONTRADICTS", "SUPPORTS", "BECAUSE_OF", "DERIVED_FROM")
    U = nx.Graph()
    U.add_edges_from((a, b) for a, b in g.ro_query(
        "MATCH (a)-[r]->(b) WHERE type(r) IN $rels RETURN a.id, b.id", {"rels": list(rels)}).result_set)
    t = tools.trace_document(g, "PR-412")
    assert t["reaches"]
    for d in t["reaches"]:
        assert d["hops"] == nx.shortest_path_length(U, "PR-412", d["id"]), d["id"]


def test_the_graph_is_load_bearing(g):
    """Remove the one contradiction edge on D01's reason and D01 holds again; put it back and it is moot. No rule changed."""
    assert tools.audit_decision(g, "D01", spec.AS_OF)["verdict"] == "MOOT"
    edge = g.ro_query("MATCH (e:Evidence {id: 'PR-412'})-[r:CONTRADICTS]->(p:Premise) RETURN p.id, properties(r)").result_set[0]
    g.query("MATCH (e:Evidence {id: 'PR-412'})-[r:CONTRADICTS]->() DELETE r")
    try:
        assert tools.audit_decision(g, "D01", spec.AS_OF)["verdict"] != "MOOT"
    finally:
        g.query("MATCH (e:Evidence {id: 'PR-412'}), (p:Premise {id: $p}) CREATE (e)-[r:CONTRADICTS]->(p) SET r = $props",
                {"p": edge[0], "props": edge[1]})
    assert tools.audit_decision(g, "D01", spec.AS_OF)["verdict"] == "MOOT"
