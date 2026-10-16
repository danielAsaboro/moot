"""Retrieval eval: does each method surface the evidence that invalidates a decision's premise?

For every decision whose ground truth is MOOT or DISPUTED, the target is the set of documents that
CONTRADICT one of its premises (truth.json). Three methods try to find them:

  graph    Moot's audit_decision path query (Decision -> premises up to 4 hops <- CONTRADICTS evidence)
  bm25     a RAG-style retriever: BM25 over every non-ADR document, query = decision title + summary, top-k
  random   k documents drawn at random (the control), averaged over 20 seeds

Reported: recall@k of the invalidating documents, and the share of decisions where at least one was found.
No model is involved, so this runs anywhere with a seeded FalkorDB. `eval/eval_e2e.py` is the model-based follow-up.
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

from rank_bm25 import BM25Okapi

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from moot import tools  # noqa: E402
from moot.graph import graph  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
truth = json.loads((ROOT / "data" / "truth.json").read_text())
K = 5


def tok(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def main() -> None:
    g = graph()
    docs = [e for e in truth["evidence"]]
    corpus_text = [f"{e['title']} {e['text']}" for e in docs]
    bm25 = BM25Okapi([tok(t) for t in corpus_text])
    targets = {}
    for d in truth["decisions"]:
        pids = set(d["premises"])
        # follow derived_from so deeper premises count, as the graph does
        changed = True
        while changed:
            changed = False
            for p in truth["premises"]:
                if p["id"] in pids and p.get("derived_from") and p["derived_from"] not in pids:
                    pids.add(p["derived_from"]); changed = True
        hits = {e["id"] for e in docs if e.get("rel") == "CONTRADICTS" and e["premise"] in pids}
        if hits:
            targets[d["id"]] = hits
    rows = []
    rng_scores = []
    for did, hits in targets.items():
        d = next(x for x in truth["decisions"] if x["id"] == did)
        a = tools.audit_decision(g, did, truth["as_of"], 4)
        found_graph = {e["id"] for p in a["premises"] for e in p["evidence"] if e["rel"] == "CONTRADICTS"}
        scores = bm25.get_scores(tok(f"{d['title']} {d['summary']}"))
        top = [docs[i]["id"] for i in sorted(range(len(docs)), key=lambda i: -scores[i])[:K]]
        found_bm25 = set(top) & hits
        rnd = []
        for seed in range(20):
            r = random.Random(seed)
            rnd.append(len(set(r.sample([x["id"] for x in docs], K)) & hits) / len(hits))
        rng_scores.append(sum(rnd) / len(rnd))
        rows.append(dict(id=did, title=d["title"], targets=sorted(hits), graph=len(found_graph & hits) / len(hits),
                         bm25=len(found_bm25) / len(hits), bm25_top=top))
    n = len(rows)
    g_recall = sum(r["graph"] for r in rows) / n
    b_recall = sum(r["bm25"] for r in rows) / n
    r_recall = sum(rng_scores) / n
    g_any = sum(1 for r in rows if r["graph"] > 0) / n
    b_any = sum(1 for r in rows if r["bm25"] > 0) / n
    out = ["# Retrieval eval: finding the evidence that kills a premise", "",
           f"Decisions with at least one invalidating document (ground truth MOOT or DISPUTED): **{n}**. k = {K}. Corpus: {len(docs)} non-ADR documents.", "",
           "| method | recall@5 of invalidating docs | decisions with ≥1 found |", "|---|---|---|",
           f"| graph path query (Moot) | **{g_recall:.2f}** | **{g_any:.0%}** |",
           f"| BM25 top-5, query = decision title + summary | {b_recall:.2f} | {b_any:.0%} |",
           f"| random 5 docs (control, mean of 20 seeds) | {r_recall:.2f} | – |", "",
           "Why BM25 misses: the invalidating document rarely shares words with the decision. \"Cap file uploads at 10 MB\" is killed by \"Raise the API gateway body limit to 100 MB\", two premise hops away; "
           "\"Keep the monolith\" is killed by all-hands notes about headcount. Lexical and semantic similarity find documents *about* the decision; the graph finds documents about its *reasons*.", "",
           "| decision | targets | graph | bm25 | bm25 top-5 |", "|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['id']} {r['title']} | {', '.join(r['targets'])} | {r['graph']:.0%} | {r['bm25']:.0%} | {', '.join(r['bm25_top'])} |")
    out += ["", "Limits: the corpus is synthetic and small; BM25 is a strong but not state-of-the-art baseline (no embeddings, by design, so the number reproduces without a model); "
            "a retriever given the *premise text* instead of the decision would do better, but a RAG system does not know the premise exists. That is the point."]
    (ROOT / "eval" / "results.md").write_text("\n".join(out) + "\n")
    print("\n".join(out[:10]))


if __name__ == "__main__":
    main()
