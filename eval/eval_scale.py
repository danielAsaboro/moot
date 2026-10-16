"""Scaling and verdict eval: does the graph keep finding the killing evidence as the corpus grows,
and how do verdicts compare with a retrieval-only baseline?

Two measurements, no model involved, so they reproduce anywhere with a FalkorDB:

1. Noise scaling. The corpus is padded with N extra documents about the same systems and vocabulary
   (templated PRs, tickets, chat, docs touching no premise). For each N:
     graph   recall@k of the invalidating documents via audit_decision on a graph seeded with the padded corpus,
             plus the median audit and the full-ledger latency in FalkorDB
     bm25    recall@k with query = decision title + summary over the padded corpus
   Noise cannot touch a premise, so the graph's recall is expected to stay flat; the point is that the
   latency stays flat too, and that the baseline degrades.

2. Verdicts. Ground truth is the `expected` verdict per decision in the spec. The graph verdict is the
   deterministic path rule. The baseline is a retrieval-only staleness detector a RAG system could run
   without a model: a decision is flagged stale when any of its BM25 top-k documents is dated after the
   decision and contains a change cue ("raise", "no longer", "roll back", ...). Precision and recall of
   the MOOT/DISPUTED class are reported for both.

Writes eval/results_scale.md.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import time
from pathlib import Path

from rank_bm25 import BM25Okapi

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from moot import tools  # noqa: E402
from moot.corpus import spec  # noqa: E402
from moot.graph import connect, ensure_schema, seed  # noqa: E402
from moot.ingest.build_graph import build  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
truth = json.loads((ROOT / "data" / "truth.json").read_text())
K = 5
NOISE = [0, 1000, 5000, 20000]
CUES = re.compile(r"\b(rais|remov|drop|replac|no longer|retir|roll(ed|ing)? back|enabl|disabl|switch|migrat|deprecat|increas|lift|chang)", re.I)


def tok(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def targets_by_decision() -> dict[str, set[str]]:
    out = {}
    for d in truth["decisions"]:
        pids = set(d["premises"])
        changed = True
        while changed:
            changed = False
            for p in truth["premises"]:
                if p["id"] in pids and p.get("derived_from") and p["derived_from"] not in pids:
                    pids.add(p["derived_from"]); changed = True
        hits = {e["id"] for e in truth["evidence"] if e.get("rel") == "CONTRADICTS" and e["premise"] in pids}
        if hits:
            out[d["id"]] = hits
    return out


def padded_truth(n: int) -> dict:
    """truth.json plus n extra noise documents with ids that cannot collide."""
    extra = [dict(id=f"{i}-x{n}", kind=k, date=dt, author=a, title=t, text=x, rel=None, premise=None)
             for (i, k, dt, a, t, x) in spec.noise_documents(n, seed=11)]
    t = dict(truth)
    t["evidence"] = truth["evidence"] + extra
    return t


def bm25_recall(docs: list[dict], targets: dict[str, set[str]]) -> float:
    bm = BM25Okapi([tok(f"{e['title']} {e['text']}") for e in docs])
    ids = [e["id"] for e in docs]
    rec = []
    for did, hits in targets.items():
        d = next(x for x in truth["decisions"] if x["id"] == did)
        scores = bm.get_scores(tok(f"{d['title']} {d['summary']}"))
        top = {ids[i] for i in sorted(range(len(ids)), key=lambda i: -scores[i])[:K]}
        rec.append(len(top & hits) / len(hits))
    return sum(rec) / len(rec)


def baseline_stale(docs: list[dict]) -> dict[str, bool]:
    """Retrieval-only staleness: a later document in the top-k with a change cue."""
    bm = BM25Okapi([tok(f"{e['title']} {e['text']}") for e in docs])
    flagged = {}
    for d in truth["decisions"]:
        scores = bm.get_scores(tok(f"{d['title']} {d['summary']}"))
        top = [docs[i] for i in sorted(range(len(docs)), key=lambda i: -scores[i])[:K]]
        flagged[d["id"]] = any(e["date"] > d["decided_on"] and CUES.search(f"{e['title']} {e['text']}") for e in top)
    return flagged


def prf(pred: dict[str, bool], gold: dict[str, bool]) -> tuple[float, float, float]:
    tp = sum(1 for k in gold if pred[k] and gold[k])
    fp = sum(1 for k in gold if pred[k] and not gold[k])
    fn = sum(1 for k in gold if not pred[k] and gold[k])
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def main() -> None:
    db = connect()
    targets = targets_by_decision()
    scale_rows = []
    tmp = ROOT / "eval" / ".graph_eval.json"
    for n in NOISE:
        t = padded_truth(n)
        gj = build(t)
        tmp.write_text(json.dumps(gj))
        g = db.select_graph(f"moot_eval_{n}")
        t0 = time.perf_counter()
        seed(g, tmp, fresh=True)
        seed_s = time.perf_counter() - t0
        # graph recall and latency
        rec, lat = [], []
        for did, hits in targets.items():
            t0 = time.perf_counter()
            a = tools.audit_decision(g, did, truth["as_of"], 4)
            lat.append((time.perf_counter() - t0) * 1000)
            found = {e["id"] for p in a["premises"] for e in p["evidence"] if e["rel"] == "CONTRADICTS"}
            rec.append(len(found & hits) / len(hits))
        t0 = time.perf_counter(); tools.ledger(g, truth["as_of"], 4); ledger_ms = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter(); tools.trace_document(g, "PR-412"); trace_ms = (time.perf_counter() - t0) * 1000
        docs = t["evidence"]
        scale_rows.append(dict(n=n, docs=len(docs), nodes=len(gj["nodes"]), edges=len(gj["edges"]), seed_s=seed_s,
                               graph=sum(rec) / len(rec), bm25=bm25_recall(docs, targets),
                               audit_ms=statistics.median(lat), ledger_ms=ledger_ms, trace_ms=trace_ms))
        g.delete()
    tmp.unlink(missing_ok=True)

    # verdicts on the real demo graph
    g = db.select_graph("moot_eval_verdicts")
    seed(g, None, fresh=True)
    gold = {d["id"]: d["expected"] for d in truth["decisions"]}
    graph_v = {r["id"]: r["verdict"] for r in tools.ledger(g, truth["as_of"], 4)}
    g.delete()
    exact = sum(1 for k in gold if graph_v.get(k) == gold[k])
    stale_gold = {k: gold[k] in ("MOOT", "DISPUTED") for k in gold}
    stale_graph = {k: graph_v.get(k) in ("MOOT", "DISPUTED") for k in gold}
    stale_base = baseline_stale(truth["evidence"])
    pg = prf(stale_graph, stale_gold)
    pb = prf(stale_base, stale_gold)
    confusion = {}
    for k in gold:
        confusion[(gold[k], graph_v.get(k))] = confusion.get((gold[k], graph_v.get(k)), 0) + 1

    out = ["# Scaling and verdict eval", "",
           "## 1. Noise scaling", "",
           f"The corpus is padded with N templated documents about the same systems (touching no premise). k = {K}. "
           f"Targets: the {sum(len(v) for v in targets.values())} documents that contradict a premise of the {len(targets)} MOOT/DISPUTED decisions. "
           "Latencies are wall-clock from the Python client to an embedded FalkorDB on one laptop core; seed time is the idempotent MERGE import.", "",
           "| extra noise docs | documents | graph nodes / edges | seed (s) | graph recall@5 | BM25 recall@5 | audit p50 (ms) | full ledger (ms) | SPpaths trace (ms) |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in scale_rows:
        out.append(f"| {r['n']:,} | {r['docs']:,} | {r['nodes']:,} / {r['edges']:,} | {r['seed_s']:.1f} | **{r['graph']:.2f}** | {r['bm25']:.2f} | {r['audit_ms']:.1f} | {r['ledger_ms']:.0f} | {r['trace_ms']:.1f} |")
    out += ["", "Reading it: the graph's recall is flat by construction (noise never touches a premise, and the audit walks premises, not text), "
            "and its latency is flat because the audit is an index lookup plus a bounded path expansion, independent of corpus size. "
            "BM25's recall on this templated noise also stays put: its misses are not a crowding problem but a vocabulary one, the killing document "
            "does not share words with the decision at any corpus size. The seed column is the honest cost: a labelled MERGE import of 20k documents "
            "takes about a second; an earlier unlabelled version took three minutes, which is why the import now names labels on both ends of every edge.", "",
            "## 2. Verdicts against ground truth", "",
            f"Ground truth is the expected verdict per decision in `moot/corpus/spec.py` ({len(gold)} decisions). "
            f"The graph rule gets **{exact}/{len(gold)}** exactly right.", "",
            "Staleness detection (is the decision MOOT or DISPUTED?), compared with a retrieval-only baseline that flags a decision when a later "
            "document in its BM25 top-5 carries a change cue such as \"raise\", \"no longer\" or \"roll back\":", "",
            "| method | precision | recall | F1 |", "|---|---|---|---|",
            f"| graph path rule (Moot) | **{pg[0]:.2f}** | **{pg[1]:.2f}** | **{pg[2]:.2f}** |",
            f"| BM25 top-5 + change-cue heuristic | {pb[0]:.2f} | {pb[1]:.2f} | {pb[2]:.2f} |", "",
            "Confusion (expected → graph):", ""]
    out += [f"- {a} → {b}: {c}" for (a, b), c in sorted(confusion.items())]
    out += ["", "Limits: synthetic corpus; the baseline has no model, by design, so the whole file reproduces offline. "
            "A model-judged RAG baseline is in `eval/eval_e2e.py` and needs an API key. The ground truth and the graph share the same spec, "
            "so the 30/30 says the verdict rule and the ingest are consistent, not that extraction from raw text is solved (see `moot/ingest/extract.py`)."]
    (ROOT / "eval" / "results_scale.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
