"""Answers and official judging. Same model, same prompt, same 10 documents per arm; Canon's settings throughout.

Answering: Canon's system prompt and context rendering (4,000-character window per document), claude-sonnet-5.
Judging: the benchmark's own scorer, run from a checkout of github.com/onyx-dot-app/EnterpriseRAG-Bench:
  LLM_PROVIDER=anthropic LLM_MODEL_NAME=claude-sonnet-4-6 \
  python -m src.scripts.answer_evaluation.metrics_based_eval --answers-file X.jsonl --questions-file Q.jsonl \
      --no-correction --parallelism 2 --results-file R.json
A failed judge call is scored as incorrect by that harness, so every run counts empty verdicts and reports them.
Without ANTHROPIC_API_KEY nothing here runs; the report says so and gives the command.
"""
from __future__ import annotations

import json
import os
import random
import statistics
import subprocess
import sys
from pathlib import Path

from moot.bench_erag import DATA, ROOT
from moot.bench_erag.corpus import Corpus, window

ANSWER_MODEL = os.getenv("MOOT_ERAG_ANSWER_MODEL", "claude-sonnet-5")
JUDGE_MODEL = os.getenv("MOOT_ERAG_JUDGE_MODEL", "claude-sonnet-4-6")
HARNESS = Path(os.getenv("MOOT_ERAG_HARNESS", ROOT.parent / "erag-harness"))
RUNS = int(os.getenv("MOOT_ERAG_JUDGE_RUNS", "3"))
OUT = ROOT / "evidence" / "erag"
SET = ("conflicting_info", "info_not_found")
SYSTEM = ("You answer questions about an enterprise using only the provided context documents. Give a direct answer with the "
          "specific values asked for. If the context does not contain enough information to answer, reply with exactly UNKNOWN "
          "and nothing else.")
COMMAND = "ANTHROPIC_API_KEY=... python3 eval/eval_erag.py --answer --judge   # or: make erag-judged"


def render(c: Corpus, ids: list[str], question: str) -> str:
    parts = []
    for i, d in enumerate(ids, 1):
        doc = c.doc(d)
        parts.append(f"[Document {i}] source={doc.source_type} id={doc.doc_id}\nTitle: {doc.title}\n{window(doc.content, question)}")
    return "\n\n".join(parts)


def ask(client, question: str, context: str) -> str:
    r = client.messages.create(model=ANSWER_MODEL, max_tokens=2048, system=SYSTEM, output_config={"effort": "medium"},
                               messages=[{"role": "user", "content": f"Context documents:\n\n{context}\n\nQuestion: {question}\n\nAnswer:"}])
    return "".join(b.text for b in r.content if b.type == "text").strip()


def bootstrap(delta: list[float], b: int = 5000, seed: int = 7) -> tuple[float, float]:
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(delta, k=len(delta))) for _ in range(b))
    return means[int(0.025 * b)], means[int(0.975 * b)]


def not_run(reason: str) -> dict:
    return dict(not_run=reason, command=COMMAND, lines=[
        "## Answer level (model-judged): not run\n",
        f"{reason}, so no answers were generated and nothing was judged. Every number above is deterministic. To run the "
        f"answer level (answer model `{ANSWER_MODEL}` with Canon's prompt, official judge `{JUDGE_MODEL}` through "
        f"`metrics_based_eval --no-correction --parallelism 2`, {RUNS} judge runs per arm, per-type correctness with "
        "ranges, empty verdicts counted, paired bootstrap 95% interval on each arm's delta against the baseline), use a "
        "checkout of github.com/onyx-dot-app/EnterpriseRAG-Bench at `../erag-harness`:\n",
        f"```bash\n{COMMAND}\n```\n"])


def run(ctx: dict, gold: dict, do_answer: bool, do_judge: bool, arms=("baseline", "moot", "random", "oracle")) -> dict:
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        return not_run("No `ANTHROPIC_API_KEY` was available for this run")
    import anthropic
    OUT.mkdir(parents=True, exist_ok=True)
    qids = sorted(q for q, g in gold.items() if g["question_type"] in SET)
    if do_answer:
        client, c = anthropic.Anthropic(), Corpus()
        for arm in arms:
            rows = [dict(question_id=q, answer=ask(client, gold[q]["question"], render(c, ctx[arm][q], gold[q]["question"])),
                         document_ids=ctx[arm][q]) for q in qids]
            (OUT / f"{arm}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    qfile = OUT / "questions.jsonl"
    qfile.write_text("".join(json.dumps(gold[q]) + "\n" for q in qids))
    verdicts: dict[str, list[dict[str, bool]]] = {a: [] for a in arms}
    failures: dict[str, list[int]] = {a: [] for a in arms}
    if do_judge:
        env = dict(os.environ, LLM_PROVIDER="anthropic", LLM_MODEL_NAME=JUDGE_MODEL)
        for run_i in range(1, RUNS + 1):
            for arm in arms:
                res = OUT / f"results-{arm}-run{run_i}.json"
                subprocess.run([sys.executable, "-m", "src.scripts.answer_evaluation.metrics_based_eval",
                                "--answers-file", str(OUT / f"{arm}.jsonl"), "--questions-file", str(qfile),
                                "--results-file", str(res), "--no-correction", "--parallelism", "2"],
                               cwd=HARNESS, env=env, check=True)
                qs = json.loads(res.read_text())["questions"]
                verdicts[arm].append({x["question_id"]: bool(x["answer_correct"]) for x in qs})
                failures[arm].append(sum(1 for x in qs if not x.get("correctness_reasoning")))
    return summarise(verdicts, failures, gold, qids)


def summarise(verdicts: dict, failures: dict, gold: dict, qids: list[str]) -> dict:
    lines = ["## Answer level (official scorer, model-judged)\n",
             f"Answer model `{ANSWER_MODEL}`, judge `{JUDGE_MODEL}` via `metrics_based_eval --no-correction`, {RUNS} judge runs. "
             "Correct answers out of 20 per type: mean and range over runs. Empty verdicts (judge failures) are counted.\n",
             "| arm | conflicting_info | info_not_found | total /40 | empty verdicts |", "|---|---|---|---|---|"]
    for arm, runs in verdicts.items():
        if not runs:
            continue
        cells = []
        for t in SET + (None,):
            vals = [sum(r[q] for q in qids if t is None or gold[q]["question_type"] == t) for r in runs]
            cells.append(f"{statistics.fmean(vals):.1f} ({min(vals)}–{max(vals)})")
        lines.append(f"| {arm} | " + " | ".join(cells) + f" | {sum(failures[arm])} |")
    out = dict(lines=lines)
    if verdicts.get("baseline") and verdicts.get("moot"):
        mean = lambda arm, q: statistics.fmean(r[q] for r in verdicts[arm])  # noqa: E731
        for arm in ("moot", "oracle", "random"):
            if verdicts.get(arm):
                d = [mean(arm, q) - mean("baseline", q) for q in qids]
                lo, hi = bootstrap(d)
                lines.append(f"\n{arm} − baseline, correct answers per question averaged over judge runs: "
                             f"{sum(d):+.1f}/{len(qids)}, paired bootstrap 95% interval {lo * len(qids):+.1f} to {hi * len(qids):+.1f}.")
    lines.append("")
    return out
