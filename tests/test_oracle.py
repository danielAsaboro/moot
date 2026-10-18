"""2,000 random worlds: the verdict FalkorDB's path query gives equals the verdict of a plain-Python walk over the same edges.

Each world is a small random company: decisions, reasons that derive from other reasons, dated SUPPORTS and CONTRADICTS
(some stated later than they took effect), and the odd SUPERSEDES. All worlds go into one graph as separate components.
For every decision, at a random date and depth, `tools.audit_decision` (the Cypher in the README) must agree with the oracle:
breadth-first over BECAUSE_OF then DERIVED_FROM up to `depth` hops, events known by `as_of`, the same pure rules in
moot/verdict.py. The rules are shared on purpose; what this checks is the traversal and the date filtering. True by
construction if the query is right, which is the point. Integration: needs FalkorDB."""
import json
import random

import pytest

from moot import tools
from moot.graph import connect, seed
from moot.verdict import decision_verdict, premise_state

pytestmark = pytest.mark.integration
WORLDS = 2000
DATES = [f"2024-{m:02d}-01" for m in range(1, 13)] + [f"2025-{m:02d}-01" for m in range(1, 13)]


def world(w: int, rng: random.Random) -> tuple[list, list, dict]:
    ids = lambda p, n: [f"w{w}_{p}{i}" for i in range(n)]
    decs, prems, evs = ids("d", rng.randint(1, 4)), ids("p", rng.randint(1, 6)), ids("e", rng.randint(0, 6))
    nodes = [dict(label="Decision", id=d, props=dict(title=d, summary="", decided_on=rng.choice(DATES[:6]))) for d in decs]
    nodes += [dict(label="Premise", id=p, props=dict(text=p)) for p in prems]
    nodes += [dict(label="Evidence", id=e, props=dict(title=e, kind="doc", date=DATES[0])) for e in evs]
    edges, adj = [], {}
    for d in decs:
        for p in rng.sample(prems, rng.randint(0, min(2, len(prems)))):
            edges.append(dict(src=d, rel="BECAUSE_OF", dst=p, props={})); adj.setdefault(d, []).append(p)
    for i, p in enumerate(prems):  # a DAG: a reason derives only from later-numbered reasons
        for q in rng.sample(prems[i + 1:], rng.randint(0, min(2, len(prems) - i - 1))):
            edges.append(dict(src=p, rel="DERIVED_FROM", dst=q, props={})); adj.setdefault(p, []).append(q)
    events = {}
    for e in evs:
        for p in rng.sample(prems, rng.randint(1, min(2, len(prems)))):
            at = rng.choice(DATES)
            props = dict(at=at)
            if rng.random() < 0.25:
                props["stated"] = rng.choice([x for x in DATES if x >= at])
            rel = rng.choice(("SUPPORTS", "CONTRADICTS"))
            edges.append(dict(src=e, rel=rel, dst=p, props=props))
            events.setdefault(p, []).append(dict(rel=rel, **props))
    sup = {}
    if len(decs) > 1 and rng.random() < 0.3:
        at = rng.choice(DATES)
        edges.append(dict(src=decs[0], rel="SUPERSEDES", dst=decs[1], props=dict(at=at)))
        sup[decs[1]] = at
    return nodes, edges, dict(decs=decs, adj=adj, events=events, sup=sup, decided={n["id"]: n["props"]["decided_on"] for n in nodes if n["label"] == "Decision"})


def oracle(wd: dict, d: str, as_of: str, depth: int) -> str:
    if wd["decided"][d] > as_of:
        return "NOT_YET"
    seen, frontier = set(), [d]
    for _ in range(depth):
        frontier = [q for x in frontier for q in wd["adj"].get(x, [])]
        seen |= set(frontier)
    known = lambda e: e["at"] <= as_of and e.get("stated", e["at"]) <= as_of
    states = [dict(state=premise_state([e for e in wd["events"].get(p, []) if known(e)])) for p in seen]
    return decision_verdict(states, superseded=d in wd["sup"] and wd["sup"][d] <= as_of)


@pytest.fixture(scope="module")
def worlds(tmp_path_factory):
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    rng = random.Random(20261021)
    nodes, edges, wds = [], [], []
    for w in range(WORLDS):
        n, e, wd = world(w, rng)
        nodes += n; edges += e; wds.append(wd)
    f = tmp_path_factory.mktemp("oracle") / "graph.json"
    f.write_text(json.dumps(dict(nodes=nodes, edges=edges)))
    g = db.select_graph("moot_test_oracle")
    seed(g, f, fresh=True)
    yield g, wds, rng
    g.delete()


def test_path_query_verdicts_equal_the_oracle_in_2000_worlds(worlds):
    g, wds, rng = worlds
    checked, wrong, kinds = 0, [], {}
    for wd in wds:
        for d in wd["decs"]:
            as_of, depth = rng.choice(DATES), rng.randint(1, 4)
            got = tools.audit_decision(g, d, as_of, depth)["verdict"]
            want = oracle(wd, d, as_of, depth)
            checked += 1
            kinds[want] = kinds.get(want, 0) + 1
            if got != want:
                wrong.append((d, as_of, depth, got, want))
    assert checked > 3000 and not wrong, wrong[:5]
    assert all(kinds.get(k, 0) > 100 for k in ("HOLDS", "MOOT", "DISPUTED", "UNDOCUMENTED", "NOT_YET")), kinds  # not a trivial agreement
