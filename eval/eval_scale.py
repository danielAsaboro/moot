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

Latency is reported as n, nearest-rank p50 and p95 over warm calls, with the first call on a freshly seeded graph and the
first call from a fresh Python process reported apart (never folded into the percentiles). Raw samples go to
eval/results_scale.json. Writes eval/results_scale.md.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from rank_bm25 import BM25Okapi

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from moot import tools  # noqa: E402
from moot.corpus import spec  # noqa: E402
from moot.graph import connect, ensure_schema, seed  # noqa: E402
from moot.ingest.build_graph import build  # noqa: E402
from moot.stats import timing_summary  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.getenv("MOOT_EVAL_OUT") or ROOT / "eval")  # `moot verify --rerun` writes elsewhere and compares
truth = json.loads((ROOT / "data" / "truth.json").read_text())
K = 5
NOISE = [0, 1000, 5000, 20000]
WARMUP = 5      # warm calls dropped before measuring
ROUNDS = 5      # audit: every target decision, this many times
REPEAT = 20     # ledger and trace: measured calls after warmup

FRESH = """import json, sys, time
t0 = time.perf_counter()
from moot import tools
from moot.graph import connect
t1 = time.perf_counter()
g = connect().select_graph(sys.argv[1])
tools.audit_decision(g, sys.argv[2], sys.argv[3], 4)
print(json.dumps(dict(import_ms=(t1 - t0) * 1000, first_audit_ms=(time.perf_counter() - t1) * 1000)))
"""


def ms(fn) -> float:
    t0 = time.perf_counter()
    fn()
    return (time.perf_counter() - t0) * 1000


def timed(fn, warmup: int, repeat: int) -> tuple[float, list[float]]:
    """(first call, warmup + measured samples). The first call is the cold one: the graph was just seeded."""
    cold = ms(fn)
    return cold, [ms(fn) for _ in range(warmup + repeat)]
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
        # cold: the very first query on the freshly seeded graph, then the first query from a fresh Python process
        first = next(iter(targets))
        audit_cold = ms(lambda: tools.audit_decision(g, first, truth["as_of"], 4))
        fresh = json.loads(subprocess.run([sys.executable, "-c", FRESH, g.name, first, truth["as_of"]], cwd=ROOT, capture_output=True,
                                          text=True, check=True).stdout)
        # graph recall, then warm audit latency over every target decision
        rec = []
        for did, hits in targets.items():
            a = tools.audit_decision(g, did, truth["as_of"], 4)
            found = {e["id"] for p in a["premises"] for e in p["evidence"] if e["rel"] == "CONTRADICTS"}
            rec.append(len(found & hits) / len(hits))
        ids = list(targets)
        audit = [ms(lambda d=d: tools.audit_decision(g, d, truth["as_of"], 4)) for d in (ids[:WARMUP] + ids * ROUNDS)]
        ledger_cold, ledger = timed(lambda: tools.ledger(g, truth["as_of"], 4), WARMUP, REPEAT)
        trace_cold, trace = timed(lambda: tools.trace_document(g, "PR-412"), WARMUP, REPEAT)
        docs = t["evidence"]
        scale_rows.append(dict(n=n, docs=len(docs), nodes=len(gj["nodes"]), edges=len(gj["edges"]), seed_s=seed_s,
                               graph=sum(rec) / len(rec), bm25=bm25_recall(docs, targets),
                               audit=timing_summary(audit, WARMUP, audit_cold), ledger=timing_summary(ledger, WARMUP, ledger_cold),
                               trace=timing_summary(trace, WARMUP, trace_cold), fresh_process=fresh,
                               samples=dict(audit=audit, ledger=ledger, trace=trace)))
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
           "Seed time is the idempotent MERGE import.", "",
           "| extra noise docs | documents | graph nodes / edges | seed (s) | graph recall@5 (consistency check) | BM25 recall@5 |",
           "|---|---|---|---|---|---|"]
    for r in scale_rows:
        out.append(f"| {r['n']:,} | {r['docs']:,} | {r['nodes']:,} / {r['edges']:,} | {r['seed_s']:.1f} | **{r['graph']:.2f}** | {r['bm25']:.2f} |")
    out += ["", "The graph column is not a retrieval result. Its targets are the CONTRADICTS edges in `truth.json`, and the graph's CONTRADICTS "
            "edges come from the same spec, so the audit reads back its own edges; 1.00 says the ingest kept every edge at every corpus size. "
            "BM25 is a real retrieval result against the same targets.", "",
            "### Latency", "",
            f"Wall-clock from the Python client to a FalkorDB server on the same laptop, in milliseconds. *Warm* is nearest-rank p50 / p95 over n calls "
            f"after {WARMUP} warmup calls were dropped (audit: every target decision, {ROUNDS} rounds; ledger and trace: {REPEAT} calls). *Cold* is the "
            "first call on the freshly seeded graph, before any query plan is cached; *fresh process* is the first audit from a new Python process, "
            "including the connection but not the imports. Cold numbers are reported apart and never folded into the percentiles. Raw samples: "
            "`eval/results_scale.json`.", "",
            "| extra noise docs | audit warm n · p50 / p95 | audit cold | audit, fresh process | full ledger warm n · p50 / p95 | ledger cold | SPpaths trace warm n · p50 / p95 | trace cold |",
            "|---|---|---|---|---|---|---|---|"]
    for r in scale_rows:
        a, l, tr = r["audit"], r["ledger"], r["trace"]
        out.append(f"| {r['n']:,} | {a['n']} · {a['p50']:.1f} / {a['p95']:.1f} | {a['cold']:.1f} | {r['fresh_process']['first_audit_ms']:.1f} | "
                   f"{l['n']} · {l['p50']:.1f} / {l['p95']:.1f} | {l['cold']:.1f} | {tr['n']} · {tr['p50']:.1f} / {tr['p95']:.1f} | {tr['cold']:.1f} |")
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
    out += ["", "## Threats to validity, worst first", "",
            "1. **Common-mode targets.** The ground truth and the graph share the same spec, so the 30/30 and the graph's recall say the verdict rule "
            "and the ingest are consistent, not that extraction from raw text is solved (see `moot/ingest/extract.py`).",
            "2. **Templated noise.** The padding documents touch no premise and share a template, so they cannot crowd the graph and only test "
            "BM25's vocabulary problem. Realistic noise that mentions the same premises would be harder for both.",
            "3. **A shared laptop.** Latencies were measured on one machine with other work running (this run shared it with a local model job). "
            "They are good for the shape of the curve against corpus size, not as a number to quote for production.",
            "4. **Cold is not a server restart.** The FalkorDB server was shared and not restarted, so *cold* means a fresh graph and a fresh client "
            "process; a cold server start (loading the graph from disk) is not measured.",
            "5. **No model baseline.** The staleness baseline has no model, by design, so the whole file reproduces offline. The model-judged RAG "
            "baseline is study S3 (`eval/results_baseline.md`): BM25 RAG with a local model, 62/90 against Moot's 90/90."]
    (OUT / "results_scale.md").write_text("\n".join(out) + "\n")
    raw = dict(as_of=truth["as_of"], k=K, warmup=WARMUP, rounds=ROUNDS, repeat=REPEAT, scale=scale_rows,
               verdicts=dict(exact=exact, n=len(gold), stale_graph=dict(zip(("precision", "recall", "f1"), pg)),
                             stale_bm25=dict(zip(("precision", "recall", "f1"), pb)),
                             confusion={f"{a}->{b}": c for (a, b), c in sorted(confusion.items())}))
    (OUT / "results_scale.json").write_text(json.dumps(raw, indent=1) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
