"""eval/results_erag.md from the deterministic report and, when present, the judged runs."""
from __future__ import annotations

from pathlib import Path

LABEL = dict(baseline="BM25 baseline", moot="Moot blind v1 (frozen)", random="random, v1 count",
             moot_v2="Moot blind v2 (post-hoc)", random_v2="random, v2 count",
             moot_v3="Moot blind v3, local LLM (post-hoc)", random_v3="random, v3 count",
             moot_v3g="Moot blind v3-groq, Groq LLM (post-hoc)", random_v3g="random, v3-groq count",
             moot_v3l="Moot blind v3, local qwen3.8:27b (post-hoc)", random_v3l="random, v3 qwen3.8 count",
             oracle="ORACLE: Canon's setup (drop + pin)", oracle_drop="ORACLE, drop only")
ARMS_ALL = ("baseline", "moot", "random", "moot_v2", "random_v2", "moot_v3", "random_v3", "moot_v3g", "random_v3g", "moot_v3l", "random_v3l",
            "oracle_drop",
            "oracle")


def caught(det: dict, arm: str) -> list[str]:
    return [q for q, v in det[arm]["per_conflict"].items() if not v["retired_in"] and det["baseline"]["per_conflict"][q]["retired_in"]]


def v3g_line(det: dict, n: dict) -> str:
    g, cov = det["moot_v3g"], det["others_covered"]["moot_v3g"]
    harm = (f"its harm covers all {n['others']} other questions" if cov == n["others"] else
            f"its harm is partial ({cov}/{n['others']}) until the free tier's daily cap lets the rest through")
    return (f"- **v3-groq** (`{det.get('v3g_extractor', 'rules-v3-llm-posthoc+groq')}`, post-hoc, still blind) is v3's prompt and "
            f"v3's pairing rules, unchanged, with the model swapped for `{det.get('v3g_model', 'qwen/qwen3.8-27b')}` on Groq "
            f"(temperature 0, JSON mode). It caught {', '.join(caught(det, 'moot_v3g')) or 'none'}: superseded gold in context "
            f"{g['retired_gold_in_context']}/{det['counts']['conflicts']}, current gold in context "
            f"{g['current_gold_in_context']}/{det['counts']['conflicts']}, info_not_found {g['not_found_contexts_changed']}/"
            f"{n['not_found']} changed. The model read the {n['conflicts'] + n['not_found']} scored questions and {cov} of the other "
            f"{n['others']}, so {harm}: {g['others_contexts_changed']} contexts changed, {g['others_expected_docs_removed']} expected "
            "documents removed. Responses are cached in `erag-data/v3_groq_cache`; `python3 eval/erag_v3_fill.py groq --cut` resumes.")


def v3l_line(det: dict, n: dict) -> str:
    g, cov = det["moot_v3l"], det["others_covered"]["moot_v3l"]
    harm = (f"its harm covers all {n['others']} other questions" if cov == n["others"] else f"its harm is partial ({cov}/{n['others']})")
    return (f"- **v3, local qwen3.8** (`{det.get('v3l_extractor')}`, post-hoc, still blind) is v3's prompt and rules, unchanged, "
            f"with `{det.get('v3l_model')}` (ollama's nvfp4 MLX build) on this machine, thinking off, temperature 0. It caught "
            f"{', '.join(caught(det, 'moot_v3l')) or 'none'}: superseded gold in context {g['retired_gold_in_context']}/"
            f"{det['counts']['conflicts']}, current gold in context {g['current_gold_in_context']}/{det['counts']['conflicts']}, "
            f"info_not_found {g['not_found_contexts_changed']}/{n['not_found']} changed. The model read {cov} of the other "
            f"{n['others']}, so {harm}: {g['others_contexts_changed']} contexts changed, {g['others_expected_docs_removed']} expected "
            "documents removed. Cache: `erag-data/v3_local38_cache`; `python3 eval/erag_v3_fill.py local38 --cut` resumes.")


def write(det: dict, judged: dict | None, out: Path) -> None:
    ARMS = tuple(a for a in ARMS_ALL if a in det)
    n, c = det["counts"], det["counts"]["conflicts"]
    m, m2, o, b = det["moot"], det["moot_v2"], det["oracle"], det["baseline"]
    fa, cj = det["failure_analysis"], det["canon_judge_noise"]
    L = ["# EnterpriseRAG-Bench: a blind supersession graph against Canon's oracle\n",
         f"**Superseded gold document still in the 10-document context ({c} conflict questions, lower is better): "
         f"Moot blind {m['retired_gold_in_context']}/{c} · ORACLE (Canon's setup) {o['retired_gold_in_context']}/{c} · "
         f"BM25 baseline {b['retired_gold_in_context']}/{c}.**\n",
         f"Built blind, the graph removes the superseded document in {m['conflict_retired_gold_removed']} of the "
         f"{b['retired_gold_in_context']} conflicts where BM25 leaks it. Canon removes it in {o['conflict_retired_gold_removed']}, "
         "but only because its graph was seeded from an inventory written by reading each question's gold documents and gold answer. "
         "A second, post-hoc rule set (v2) also caught "
         f"{m2['conflict_retired_gold_removed']}. We report this as measured. The rules are precise but have almost no recall on how "
         "this benchmark phrases its conflicts (see *Why the blind rules miss*).\n",
         "## What each arm may read\n",
         "- **Moot blind** reads question text, the BM25 ranking it produces, and the text of the 50 documents ranked for each question. "
         "It never reads `expected_doc_ids`, `gold_answer` or `answer_facts`. `tests/test_erag.py` fails if any blind module names a "
         "gold field, or if the blind path asks the questions file for any column other than `question_id` and `question`. Both "
         "checks were mutation-tested: each fails when the blind path is made to read the answer key.",
         "- **ORACLE** reproduces Canon (github.com/Enoch208/canon). It drops the retired gold document named in Canon's "
         "`research/conflict_inventory.json`, pins the current one, and leaves the one contested claim (qst_0413) alone. Its contexts "
         "match Canon's published `canon_filtered` contexts on 20/20 questions.",
         "- Every arm answers from exactly 10 documents of the same BM25 ranking: SQLite FTS5, bm25(title 2.0, content 1.0), the "
         "question's terms OR-ed. This reproduces Canon's baseline top-10 on 20/20 conflict questions. Removals are backfilled from "
         f"the same ranking. Context documents over all 500 questions: {b['context_docs']} in every arm.\n",
         "## Deterministic (no model)\n",
         "| | " + " | ".join(LABEL[a] for a in ARMS) + " |", "|---|" + "---|" * len(ARMS)]
    rows = [
        ("Superseded gold doc in context, conflicts (lower is better)", "retired_gold_in_context", c),
        ("Current gold doc in context, conflicts", "current_gold_in_context", c),
        ("Conflict contexts changed", "conflict_contexts_changed", c),
        ("info_not_found contexts changed", "not_found_contexts_changed", n["not_found"]),
        ("Other questions: contexts changed", "others_contexts_changed", n["others"]),
        ("Other questions: documents removed", "others_docs_removed", None),
        ("Other questions: expected documents removed", "others_expected_docs_removed", None),
        ("Other questions losing an expected document", "others_questions_losing_expected_doc", n["others"]),
    ]
    cov = det.get("others_covered", {})
    for title, key, of in rows:
        def cell(a):
            d = of
            if of == n["others"] and cov.get(a, of) != of:
                d = f"{cov[a]} (partial {cov[a]}/{of})"
            elif of is None and key.startswith("others") and cov.get(a, n["others"]) != n["others"]:
                return f"{det[a][key]} (partial {cov[a]}/{n['others']})"
            return f"{det[a][key]}" + (f"/{d}" if d else "")
        L.append(f"| {title} | " + " | ".join(cell(a) for a in ARMS) + " |")
    v1c, v2c = caught(det, "moot"), caught(det, "moot_v2")
    L += ["",
          f"\"Other questions\" are the {n['others']} that are neither `conflicting_info` nor `info_not_found`. Random arms remove the "
          "same number of top-10 documents as the Moot arm they shadow, seeded per question.\n",
          "## What v1, v2 and v3 caught\n",
          f"- **v1** (`rules-v1`, frozen before its first run on any benchmark pool) caught {', '.join(v1c) or 'none'}. It drops a "
          "document only when another retrieved document retires the exact value it states: *\"changed from X to Y\"*, *\"Y (previously "
          "X)\"*, *\"X → Y\"*, *\"instead of X\"*, on a line sharing three topic words and the same identifiers, and only if the older "
          "document is not dated later. Caveat: qst_0411's spans are the one conflict example we had seen in Canon's inventory while "
          "confirming the oracle, before writing v1.",
          f"- **v2** (`rules-v2-posthoc`, written after v1 was scored, frozen before its own run, still blind) caught "
          f"{', '.join(v2c) or 'none'}. On top of v1 it pairs lines in two documents that state the same claim (shared topic words, "
          "identifiers, proper nouns, the words just before the value, and every entity the question names) with different values, "
          "and lets update language or the later date decide. It found nothing new on the conflicts. It changed "
          f"{m2['others_contexts_changed']} other contexts and removed {m2['others_expected_docs_removed']} expected documents.",
          *([f"- **v3** (`rules-v3-llm-posthoc`, written after v1 and v2 were scored, frozen before its own run, still blind) caught "
             f"{', '.join(caught(det, 'moot_v3')) or 'none'}. A local model (qwen2.5:14b-instruct, temperature 0) reads each question's "
             "top-10 documents and reports the value each gives, its status (current, superseded, proposed), any value it says it "
             "replaces, and its date. Rules decide the drop, and only when exactly two distinct values are present. The run was "
             f"stopped at Daniel's call. The model read the 40 scored questions and {det['others_covered']['moot_v3']} of the other "
             f"{n['others']}, so v3's harm is partial ({det['others_covered']['moot_v3']}/{n['others']}): "
             f"{det['moot_v3']['others_contexts_changed']} contexts changed, {det['moot_v3']['others_expected_docs_removed']} expected "
             "documents removed. Post-hoc diagnosis: the model often reports no value for the retired document even when the "
             "current one says what it replaced, and the two-value rule blocks conflicts where other documents add values."]
            if "moot_v3" in det else []),
          *([v3g_line(det, n)] if "moot_v3g" in det else []),
          *([v3l_line(det, n)] if "moot_v3l" in det else []),
          f"- Harm, v1: {m['others_contexts_changed']}/{n['others']} other contexts changed, {m['others_docs_removed']} documents "
          f"removed, {m['others_expected_docs_removed']} of them expected "
          f"({', '.join(h['question_id'] for h in det['harm_detail_moot'] if h['expected_removed']) or 'none'}). "
          f"info_not_found: {m['not_found_contexts_changed']}/{n['not_found']} changed. Each removal and the sentence that justified it "
          "is in `erag-data/blind_cut.json` (`proof`).\n",
          "## Why the blind rules miss (post-hoc, reads the answer key)\n",
          f"In all {fa['retired_in_top10']} conflicts where BM25 leaks the retired document, the current document is also in the "
          f"top 10 ({fa['current_ranked_first']} of them at rank 1). So retrieval is not the bottleneck: both sides of the conflict "
          f"are in front of the graph. The extraction is. Only {fa['current_names_retired_value']} of the {fa['retired_in_top10']} "
          "current documents repeat the retired value verbatim, which is what v1's explicit rules need. Only "
          f"{fa['retired_value_is_one_number']} of the retired values are a single number, which is what v2's same-claim pairing "
          "needs. The rest are tiers (*\"50 / 120 / 220 QPS\"*), names (*\"GPG signatures\"*), endpoints, or procedures. Catching "
          "those blind takes claim extraction that understands the sentence (an LLM pass), not value matching. "
          "Per question: `evidence/erag_deterministic.json` → `failure_analysis`.\n",
          "## Canon's 82.5% and the judge\n",
          f"Canon reports {cj['baseline_correct']}/40 → {cj['canon_filtered_correct']}/40 on the official scorer (judge "
          f"`{cj['judge']}`, one run). Its own published files show:",
          f"- All {cj['not_found_identical_in_all_three_arms']} `info_not_found` questions have byte-identical contexts and "
          "byte-identical answers in `baseline`, `canon` and `canon_filtered`. The judge still scored them "
          f"{cj['not_found_scored']['baseline']}, {cj['not_found_scored']['canon']} and {cj['not_found_scored']['canon_filtered']}/20. "
          f"It disagreed with itself on {cj['not_found_verdict_disagreements']} of the 20 identical answers.",
          f"- Only {cj['contexts_changed']} of 40 contexts differ between baseline and `canon_filtered`. Those questions account for "
          f"{cj['delta_from_changed_contexts']:+d} of the +{cj['canon_filtered_correct'] - cj['baseline_correct']}. The other "
          f"{cj['delta_from_identical_contexts']:+d} come from questions whose context did not change, "
          f"{cj['delta_from_identical_context_and_answer']:+d} of them where the answer did not change either.",
          "- The harness scores a failed judge call as incorrect, and its judge samples with thinking at temperature 1. A single "
          "judged run cannot separate a 2-question effect from this noise. That is why the judged protocol below is "
          "three runs plus a paired bootstrap.\n"]
    if judged:
        L += judged.get("lines", [])
    L += ["## Reproduce\n", "```bash",
          "make db                 # FalkorDB on :6379",
          "make erag               # fetch (1.4 GB, pinned revision) -> FTS5 index -> pools -> graphs `erag` (v1) and `erag_v2` -> this file",
          "python3 -m pytest tests/test_erag.py", "```\n",
          "Hashes of the dataset files, pools, cuts, contexts and extractors, plus the freeze record, are in "
          "`evidence/run_manifest.json`."]
    out.write_text("\n".join(L) + "\n")
