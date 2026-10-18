"""Hidden teams and who connects whom, on a small graph built for the test: three teams on paper, three groups that really
work together (one made of three teams' leads), and a chain of shared records between two people. Integration: needs FalkorDB."""
import networkx as nx
import pytest

from moot import org
from moot.graph import connect

pytestmark = pytest.mark.integration

# record -> its authors; team -> the decisions it answers for (each record is one decision's)
RECORDS = {"r1": "a b c", "r2": "a b", "r3": "b c", "r4": "d e f", "r5": "d e", "r6": "e f",
           "r7": "c g", "r8": "g h i", "r9": "h i", "r10": "g i"}
TEAM = {"t1": ["r1", "r2", "r3"], "t2": ["r4", "r5", "r6"], "t3": []}
LEADS = {"g": "t1", "h": "t2", "i": "t3"}  # the third group's people each lead a different team


@pytest.fixture(scope="module")
def g():
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    graph = db.select_graph("moot_test_org")
    graph.query("MATCH (n) DETACH DELETE n")
    people = sorted({p for ps in RECORDS.values() for p in ps.split()})
    graph.query("UNWIND $ps AS p CREATE (:Person {id: p, name: toUpper(p)})", {"ps": people})
    for r, ps in RECORDS.items():
        graph.query("CREATE (:Evidence {id: $r})<-[:RECORDED_IN]-(:Decision {id: 'd_' + $r})", {"r": r})
        graph.query("UNWIND $ps AS p MATCH (x:Person {id: p}), (e:Evidence {id: $r}) CREATE (x)-[:AUTHORED]->(e)", {"ps": ps.split(), "r": r})
    for t, rs in TEAM.items():
        graph.query("CREATE (:Team {id: $t, name: $t})", {"t": t})
        graph.query("UNWIND $rs AS r MATCH (t:Team {id: $t}), (d:Decision {id: 'd_' + r}) CREATE (t)-[:RESPONSIBLE_FOR]->(d)", {"t": t, "rs": rs})
    for p, t in LEADS.items():
        graph.query("MATCH (p:Person {id: $p}), (t:Team {id: $t}) CREATE (p)-[:LEADS {valid_from: '2020-01-01', valid_to: ''}]->(t)", {"p": p, "t": t})
    yield graph
    graph.delete()


def test_collab_pairs_are_people_who_wrote_the_same_record(g):
    pairs = org.collab_pairs(g)
    assert pairs[("a", "b")] == ["r1", "r2"] and ("a", "d") not in pairs


def test_communities_are_the_groups_that_work_together(g):
    r = org.hidden_teams(g)
    groups = sorted(sorted(c["members"]) for c in r["communities"])
    assert groups == [["A", "B", "C"], ["D", "E", "F"], ["G", "H", "I"]]
    ghi = next(c for c in r["communities"] if "G" in c["members"])
    assert ghi["hidden"] and set(ghi["teams"]) == {"t1", "t2", "t3"}  # its people lead three teams, none holds most


def test_connection_is_the_shortest_chain_like_networkx(g):
    r = org.connection(g, "a", "h")
    G = nx.Graph([(x, y) for ps in RECORDS.values() for x in ps.split() for y in ps.split() if x < y])
    assert r["found"] and r["hops"] == nx.shortest_path_length(G, "a", "h") and r["people"][0] == "A" and r["people"][-1] == "H"
    assert not org.connection(g, "a", "d")["found"]
