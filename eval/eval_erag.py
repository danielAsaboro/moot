"""EnterpriseRAG-Bench, blind vs oracle. Deterministic first; the model-judged part runs only with a key.

  python3 eval/eval_erag.py            contexts for every arm + deterministic metrics -> eval/results_erag.md
  python3 eval/eval_erag.py --answer   + answers (same model, prompt, 10 docs per arm) -> evidence/erag/<arm>.jsonl
  python3 eval/eval_erag.py --answer --judge   + score the JSONL with the benchmark's own metrics_based_eval, 3 runs

Arms, all answering from exactly 10 documents of the same BM25 ranking:
  baseline     BM25 top-10 (Canon's ranking, reproduced exactly)
  moot         blind, rules-v1 (frozen before any benchmark run): drop every top-10 document the FalkorDB graph
               proves superseded, backfill (moot/bench_erag/cut.py)
  random       drop as many top-10 documents as moot does for that question, chosen at random, backfill
  moot_v2      blind, rules-v2, POST-HOC (written after v1 was scored; still no answer key): v1 + same-claim pairs
  random_v2    random removal with moot_v2's count
  moot_v3      blind, local-LLM claim extraction + rule pairing, POST-HOC (extract_v3.py), top-10 only
  random_v3    random removal with moot_v3's count
  moot_v3g     v3's prompt and rules unchanged, model on Groq (extract_v3_groq.py), POST-HOC; harm partial until every
               question is cached (eval/erag_v3_fill.py fills the cache under the free-tier daily cap)
  random_v3g   random removal with moot_v3g's count
  oracle       ORACLE, Canon's setup: drop the hand-labelled retired gold document, pin the current one (oracle.py)
  oracle_drop  ORACLE without the pin, the like-for-like comparison with moot (drop and backfill only)

The answer key is read here, after the blind cut is fixed on disk; the blind side never imports it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from moot.bench_erag import DATA, DATASET, REVISION, TOP_K  # noqa: E402
from moot.bench_erag.cut import OUT as BLIND, fill  # noqa: E402
from moot.bench_erag.oracle import INVENTORY, inventory, oracle_context, resolves  # noqa: E402
from moot.bench_erag.questions import load_gold  # noqa: E402

RESULTS = ROOT / "eval" / "results_erag.md"
EVIDENCE = ROOT / "evidence"
CONTEXTS = DATA / "contexts.json"
COVERED: dict[str, set[str]] = {}   # arm -> questions its model actually read, when that run is partial
BLIND_V2 = DATA / "blind_cut_v2.json"
BLIND_V3 = DATA / "blind_cut_v3.json"
BLIND_V3G = DATA / "blind_cut_v3_groq.json"
BLIND_V3L = DATA / "blind_cut_v3_local38.json"
LLM_ARMS = {"moot_v3": (BLIND_V3, "random_v3", "v3"), "moot_v3g": (BLIND_V3G, "random_v3g", "v3g"),
            "moot_v3l": (BLIND_V3L, "random_v3l", "v3l")}
ARMS = ("baseline", "moot", "random", "moot_v2", "random_v2") + \
    tuple(a for arm, (path, rnd, _) in LLM_ARMS.items() if path.exists() for a in (arm, rnd)) + ("oracle", "oracle_drop")
CONFLICT, NOT_FOUND = "conflicting_info", "info_not_found"


def random_cut(qid: str, ranking: list[str], n: int, salt: str = "") -> list[str]:
    rng = random.Random(int(hashlib.sha256((salt + qid).encode()).hexdigest()[:8], 16))
    return fill(ranking, set(rng.sample(ranking[:TOP_K], n)) if n else set())


def contexts() -> dict[str, dict[str, list[str]]]:
    blind = json.loads(BLIND.read_text())["questions"]
    blind2 = json.loads(BLIND_V2.read_text())["questions"]
    llm = {}
    for arm, (path, rnd, salt) in LLM_ARMS.items():
        if path.exists():
            b = json.loads(path.read_text())
            llm[arm] = (b["questions"], rnd, salt)
            if b.get("covered") is not None:
                COVERED[arm] = COVERED[rnd] = set(b["covered"])
    pools = json.loads((DATA / "pools.json").read_text())
    inv = inventory()
    out: dict[str, dict[str, list[str]]] = {a: {} for a in ARMS}
    for qid, b in blind.items():
        ranking = pools[qid]["ranking"]
        out["baseline"][qid] = b["baseline"]
        out["moot"][qid] = b["moot"]
        out["random"][qid] = random_cut(qid, ranking, len(b["dropped_in_top10"]))
        out["moot_v2"][qid] = blind2[qid]["moot"]
        out["random_v2"][qid] = random_cut(qid, ranking, len(blind2[qid]["dropped_in_top10"]), "v2")
        for arm, (qs, rnd, salt) in llm.items():
            out[arm][qid] = qs[qid]["moot"]
            out[rnd][qid] = random_cut(qid, ranking, len(qs[qid]["dropped_in_top10"]), salt)
        if qid in inv and resolves(inv[qid]):
            c = inv[qid]
            out["oracle"][qid] = oracle_context(ranking, c["old_doc_id"], c["new_doc_id"])
            out["oracle_drop"][qid] = oracle_context(ranking, c["old_doc_id"], c["new_doc_id"], pin=False)
        else:
            out["oracle"][qid] = out["oracle_drop"][qid] = b["baseline"]
    for arm, ctx in out.items():
        assert all(len(v) == TOP_K for v in ctx.values()), f"{arm}: context budget broken"
    return out


def deterministic(ctx: dict, gold: dict) -> dict:
    inv = inventory()
    conflicts = sorted(q for q, g in gold.items() if g["question_type"] == CONFLICT)
    not_found = sorted(q for q, g in gold.items() if g["question_type"] == NOT_FOUND)
    others = sorted(q for q, g in gold.items() if g["question_type"] not in (CONFLICT, NOT_FOUND))
    base = ctx["baseline"]
    rep: dict = {"counts": dict(conflicts=len(conflicts), not_found=len(not_found), others=len(others))}
    all_others = others
    for arm in ARMS:
        a = ctx[arm]
        others = all_others
        if arm in COVERED:
            others = [q for q in all_others if q in COVERED[arm]]   # partial: only questions the model has read
        rep.setdefault("others_covered", {})[arm] = len(others)
        removed = {q: set(base[q]) - set(a[q]) for q in a}
        rep[arm] = dict(
            retired_gold_in_context=sum(inv[q]["old_doc_id"] in a[q] for q in conflicts),
            current_gold_in_context=sum(inv[q]["new_doc_id"] in a[q] for q in conflicts),
            conflict_contexts_changed=sum(a[q] != base[q] for q in conflicts),
            conflict_retired_gold_removed=sum(inv[q]["old_doc_id"] in removed[q] for q in conflicts),
            not_found_contexts_changed=sum(a[q] != base[q] for q in not_found),
            others_contexts_changed=sum(a[q] != base[q] for q in others),
            others_docs_removed=sum(len(removed[q]) for q in others),
            others_expected_docs_removed=sum(len(removed[q] & set(gold[q]["expected_doc_ids"])) for q in others),
            others_questions_losing_expected_doc=sum(bool(removed[q] & set(gold[q]["expected_doc_ids"])) for q in others),
            context_docs=sum(len(v) for v in a.values()),
        )
        rep[arm]["per_conflict"] = {q: dict(retired_in=inv[q]["old_doc_id"] in a[q], current_in=inv[q]["new_doc_id"] in a[q],
                                            changed=a[q] != base[q]) for q in conflicts}
    for arm in [a for a in ("moot", "moot_v2", "moot_v3", "moot_v3g", "moot_v3l") if a in ctx]:
        rep[f"harm_detail_{arm}"] = [dict(question_id=q, question_type=gold[q]["question_type"], removed=sorted(set(base[q]) - set(ctx[arm][q])),
                                          expected_removed=sorted((set(base[q]) - set(ctx[arm][q])) & set(gold[q]["expected_doc_ids"])))
                                     for q in others + not_found if ctx[arm][q] != base[q]]
    return rep


CANON_OFFICIAL = INVENTORY.parents[1] / "eval" / "official"


def canon_judge_noise() -> dict:
    """Canon's own official-scorer files: how much of 28 -> 33 comes from questions whose context actually changed."""
    arms = ("baseline", "canon_filtered", "canon", "random_filter")
    res = {a: {x["question_id"]: x for x in json.loads((CANON_OFFICIAL / f"results-{a}.json").read_text())["questions"]} for a in arms}
    ans = {a: {json.loads(l)["question_id"]: json.loads(l) for l in (CANON_OFFICIAL / f"{a}.jsonl").read_text().splitlines()} for a in arms}
    b, f = "baseline", "canon_filtered"
    same_ctx = [q for q in ans[b] if ans[b][q]["document_ids"] == ans[f][q]["document_ids"]]
    same_ctx_same_answer = [q for q in same_ctx if ans[b][q]["answer"] == ans[f][q]["answer"]]
    flips = lambda qs: sum(res[f][q]["answer_correct"] - res[b][q]["answer_correct"] for q in qs)  # noqa: E731
    nf = sorted(q for q in res[b] if res[b][q]["question_type"] == NOT_FOUND)
    nf_identical = [q for q in nf if len({ans[a][q]["answer"] for a in ("baseline", "canon_filtered", "canon")}) == 1
                    and len({tuple(ans[a][q]["document_ids"]) for a in ("baseline", "canon_filtered", "canon")}) == 1]
    return dict(
        baseline_correct=sum(x["answer_correct"] for x in res[b].values()),
        canon_filtered_correct=sum(x["answer_correct"] for x in res[f].values()),
        contexts_changed=len(res[b]) - len(same_ctx),
        delta_from_changed_contexts=flips([q for q in res[b] if q not in same_ctx]),
        delta_from_identical_contexts=flips(same_ctx),
        delta_from_identical_context_and_answer=flips(same_ctx_same_answer),
        not_found_identical_in_all_three_arms=len(nf_identical),
        not_found_scored={a: sum(res[a][q]["answer_correct"] for q in nf) for a in ("baseline", "canon", "canon_filtered")},
        not_found_verdict_disagreements=sum(1 for q in nf_identical
                                            if len({res[a][q]["answer_correct"] for a in ("baseline", "canon_filtered", "canon")}) > 1),
        judge=json.loads((INVENTORY.parents[1] / "evidence" / "official_eval.json").read_text())["judge_model"],
    )


def failure_analysis() -> dict:
    """POST-HOC, scoring side: why value-anchored rules miss the benchmark's conflicts (reads the answer key)."""
    from moot.bench_erag import extract as v1
    from moot.bench_erag.corpus import Corpus
    inv, pools, c = inventory(), json.loads((DATA / "pools.json").read_text()), Corpus()
    rows = {}
    for q, ci in sorted(inv.items()):
        r, o, n = pools[q]["ranking"], ci["old_doc_id"], ci["new_doc_id"]
        new_text = c.doc(n).content
        rows[q] = dict(retired_rank=r.index(o) + 1 if o in r else None, current_rank=r.index(n) + 1 if n in r else None,
                       current_doc_names_retired_value=ci["old_proposition"].lower() in new_text.lower(),
                       retired_value_is_one_number=len(v1.values(ci["old_proposition"])) == 1 and len(ci["old_proposition"]) <= 12)
    leaking = [x for x in rows.values() if x["retired_rank"] and x["retired_rank"] <= TOP_K]
    return dict(per_question=rows, retired_in_top10=len(leaking),
                current_also_in_top10=sum(1 for x in leaking if x["current_rank"] and x["current_rank"] <= TOP_K),
                current_ranked_first=sum(1 for x in leaking if x["current_rank"] == 1),
                current_names_retired_value=sum(1 for x in leaking if x["current_doc_names_retired_value"]),
                retired_value_is_one_number=sum(1 for x in leaking if x["retired_value_is_one_number"]))


def per_question(ctx: dict, gold: dict) -> list[dict]:
    """One row per (question, arm): enough to rerun the leak check without this code."""
    inv = inventory()
    rows = []
    for q in sorted(gold):
        base = ctx["baseline"][q]
        for arm in ARMS:
            c = ctx[arm][q]
            row = dict(question_id=q, question_type=gold[q]["question_type"], arm=arm, context_doc_ids=c,
                       removed=[d for d in base if d not in c], added=[d for d in c if d not in base])
            if q in inv:
                row.update(superseded_gold_doc=inv[q]["old_doc_id"], current_gold_doc=inv[q]["new_doc_id"],
                           superseded_gold_in_context=inv[q]["old_doc_id"] in c, current_gold_in_context=inv[q]["new_doc_id"] in c)
            row["expected_docs_removed"] = sorted(set(row["removed"]) & set(gold[q]["expected_doc_ids"]))
            if arm in COVERED:
                row["model_read_this_question"] = q in COVERED[arm]
            rows.append(row)
    return rows


def llm_manifest(path: Path, gold: dict) -> dict:
    b = json.loads(path.read_text())
    others = [q for q, g in gold.items() if g["question_type"] not in (CONFLICT, NOT_FOUND)]
    cov = b.get("covered")
    return dict(version=b["extractor"], sha256=b["extractor_sha256"], model=b.get("model"), graph=b["graph"],
                questions_read_by_model=len(cov) if cov is not None else len(gold),
                harm_coverage=f"partial ({len(set(cov) & set(others))}/{len(others)})" if cov is not None else f"{len(others)}/{len(others)}",
                **b["graph_stats"])


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--answer", action="store_true")
    ap.add_argument("--judge", action="store_true")
    args = ap.parse_args()
    gold = load_gold()
    ctx = contexts()
    CONTEXTS.write_text(json.dumps(ctx, indent=1))
    det = deterministic(ctx, gold)
    if BLIND_V3G.exists():
        b = json.loads(BLIND_V3G.read_text())
        det["v3g_extractor"], det["v3g_model"] = b["extractor"], b.get("model")
    if BLIND_V3L.exists():
        b = json.loads(BLIND_V3L.read_text())
        det["v3l_extractor"], det["v3l_model"] = b["extractor"], b.get("model")
    det["canon_judge_noise"] = canon_judge_noise()
    det["failure_analysis"] = failure_analysis()
    EVIDENCE.mkdir(exist_ok=True)
    (EVIDENCE / "erag_deterministic.json").write_text(json.dumps(det, indent=1) + "\n")
    (EVIDENCE / "erag_per_question.jsonl").write_text("".join(json.dumps(r) + "\n" for r in per_question(ctx, gold)))
    from moot.bench_erag import answer
    judged = (answer.run(ctx, gold, do_answer=args.answer, do_judge=args.judge) if args.answer or args.judge
              else answer.not_run("This run was deterministic only (no `--answer --judge`, and no `ANTHROPIC_API_KEY` on the machine)"))
    from moot.bench_erag.report import write
    write(det, judged, RESULTS)
    blind = json.loads(BLIND.read_text())
    manifest = dict(
        generated_at=datetime.now(UTC).isoformat(), dataset=dict(repo=DATASET, revision=REVISION),
        extractor_v2=dict(version=json.loads(BLIND_V2.read_text())["extractor"], sha256=json.loads(BLIND_V2.read_text())["extractor_sha256"],
                          graph=json.loads(BLIND_V2.read_text())["graph"], **json.loads(BLIND_V2.read_text())["graph_stats"]),
        **{f"extractor_{tag}": llm_manifest(path, gold) for arm, (path, _, tag) in LLM_ARMS.items() if path.exists()},
        extractor=dict(version=blind["extractor"], sha256=blind["extractor_sha256"],
                       freeze=json.loads((DATA / "freeze.json").read_text()) if (DATA / "freeze.json").exists() else None),
        graph=dict(name=blind["graph"], **blind["graph_stats"]),
        files={os.path.relpath(p, ROOT): sha(p) for p in
               [DATA / "documents.parquet", DATA / "questions.parquet", DATA / "pools.json", BLIND, BLIND_V2, BLIND_V3, BLIND_V3G, BLIND_V3L, CONTEXTS,
                INVENTORY, ROOT / "moot/bench_erag/extract.py", ROOT / "moot/bench_erag/extract_v2.py",
                ROOT / "moot/bench_erag/extract_v3.py", ROOT / "moot/bench_erag/extract_v3_groq.py",
                ROOT / "moot/bench_erag/extract_v3_local38.py", ROOT / "moot/bench_erag/cut.py", ROOT / "moot/bench_erag/graph.py",
                EVIDENCE / "erag_deterministic.json", EVIDENCE / "erag_per_question.jsonl", RESULTS] + sorted((EVIDENCE / "erag").glob("*")) if p.exists()},
    )
    (EVIDENCE / "run_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps({a: {k: v for k, v in det[a].items() if k != "per_conflict"} for a in ARMS}, indent=1))
    print("->", RESULTS.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
