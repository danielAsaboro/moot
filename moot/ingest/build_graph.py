"""Turn truth.json (or an extractor's output of the same shape) into graph.json.

graph.json is the deterministic import format: a list of nodes and a list of edges with
stable ids, so `moot seed` can MERGE it any number of times and get the same graph.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def build(truth: dict) -> dict:
    nodes, edges = [], []

    def node(label, id, **props):
        nodes.append(dict(label=label, id=id, props=props))

    def edge(src, rel, dst, **props):
        edges.append(dict(src=src, rel=rel, dst=dst, props=props))

    for p in truth["people"]:
        node("Person", p["id"], name=p["name"], role=p["role"], joined=p["joined"], left=p["left"] or "")
    for p in truth["people"]:
        for r in p.get("reports_to", []):
            edge(p["id"], "REPORTS_TO", r["manager"], valid_from=r["valid_from"], valid_to=r["valid_to"] or "")
    for s in truth["systems"]:
        node("System", s["id"], name=s["name"])
    for p in truth["premises"]:
        node("Premise", p["id"], text=p["text"], kind=p["kind"])
        if p.get("derived_from"):
            edge(p["id"], "DERIVED_FROM", p["derived_from"])
    for d in truth["decisions"]:
        node("Decision", d["id"], title=d["title"], summary=d["summary"], decided_on=d["decided_on"], source=d["source"])
        node("Evidence", f"src:{d['id']}", kind="adr", title=f"ADR {d['id']}", date=d["decided_on"], path=d["source"], excerpt=d["summary"])
        edge(d["id"], "RECORDED_IN", f"src:{d['id']}")
        for pid in d["premises"]:
            edge(d["id"], "BECAUSE_OF", pid, quote=next(p["text"] for p in truth["premises"] if p["id"] == pid))
        owner_left = next((p["left"] for p in truth["people"] if p["id"] == d["owner"]), None)
        edge(d["owner"], "OWNS", d["id"], valid_from=d["decided_on"], valid_to=owner_left or "")
        for s in d["systems"]:
            edge(d["id"], "GOVERNS", s)
        if d.get("supersedes"):
            # dated by the superseding decision: before that day the old one was still in force
            edge(d["id"], "SUPERSEDES", d["supersedes"], at=d["decided_on"])
    for e in truth["evidence"]:
        node("Evidence", e["id"], kind=e["kind"], title=e["title"], date=e["date"], excerpt=e["text"][:280], path="")
        edge(e["author"], "AUTHORED", e["id"])
        if e.get("rel") and e.get("premise"):
            edge(e["id"], e["rel"], e["premise"], at=e["date"], quote=e["text"][:200])
    return dict(nodes=nodes, edges=edges)


def main(src: str = "truth.json", dst: str = "graph.json") -> None:
    truth = json.loads((DATA / src).read_text())
    g = build(truth)
    (DATA / dst).write_text(json.dumps(g, indent=1))
    print(f"graph: {len(g['nodes'])} nodes, {len(g['edges'])} edges -> {DATA / dst}")


if __name__ == "__main__":
    main()
