"""Fill a v3 response cache, resumably, the 40 scored questions first, then the other 460.

  python3 eval/erag_v3_fill.py groq           ask Groq for every question not yet cached; stop cleanly at the daily cap
  python3 eval/erag_v3_fill.py local          the same with v3's local ollama model
  python3 eval/erag_v3_fill.py groq --cut     then cut from the cache (MOOT_ERAG_V3_CACHE_ONLY) and rewrite results_erag.md
  python3 eval/erag_v3_fill.py groq --scored-only    stop after the 40 scored questions

The order reads question_type (scoring side) only to put conflicting_info and info_not_found first; the extractor
itself still sees question text and document text only. Progress goes to erag-data/v3_<backend>_progress.json.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from moot.bench_erag import DATA, pools  # noqa: E402
from moot.bench_erag import extract_v3, extract_v3_groq  # noqa: E402
from moot.bench_erag.corpus import Corpus  # noqa: E402
from moot.bench_erag.questions import load_gold  # noqa: E402

BACKENDS = {"groq": (extract_v3_groq, "v3-groq"), "local": (extract_v3, "v3")}
SCORED = ("conflicting_info", "info_not_found")


def order() -> list[str]:
    types = {q: v["question_type"] for q, v in load_gold().items()}
    qs = sorted(pools.load())
    return [q for q in qs if types[q] in SCORED] + [q for q in qs if types[q] not in SCORED]


def cached(g, prompt: str) -> bool:
    return (g.cache_path(prompt) if hasattr(g, "cache_path") else
            g.CACHE / f"{__import__('hashlib').sha256((g.MODEL + chr(10) + prompt).encode()).hexdigest()}.json").exists()


def fill(backend: str, scored_only: bool = False) -> dict:
    g = BACKENDS[backend][0]
    p, c, tokens, t0, stop = pools.load(), Corpus(), 0, time.time(), None
    qs = order()
    types = {q: v["question_type"] for q, v in load_gold().items()}
    prompts = {q: extract_v3_groq.prompt_for(p[q]["question"], {d: c.doc(d).content for d in p[q]["ranking"]}) for q in qs}
    for i, qid in enumerate(qs, 1):
        if scored_only and types[qid] not in SCORED:
            break
        if cached(g, prompts[qid]):
            continue
        try:
            used = g.ask(prompts[qid]).get("_usage", {})
        except extract_v3_groq.DailyCap as e:
            stop = f"daily cap at {qid} ({i - 1}/{len(qs)} done): {e}"
            break
        tokens += used.get("total_tokens", 0)
        print(f"{i}/{len(qs)} {qid} {types[qid]} tokens {used.get('total_tokens')} (run total {tokens}) {time.time() - t0:.0f}s",
              flush=True)
    have = [q for q in qs if cached(g, prompts[q])]
    prog = dict(model=g.MODEL, questions=len(qs), cached=len(have),
                scored_cached=sum(types[q] in SCORED for q in have), scored=sum(types[q] in SCORED for q in qs),
                others_cached=sum(types[q] not in SCORED for q in have), tokens_this_run=tokens, stopped=stop,
                at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    (DATA / f"v3_{backend}_progress.json").write_text(json.dumps(prog, indent=1))
    return prog


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("backend", choices=sorted(BACKENDS))
    ap.add_argument("--cut", action="store_true")
    ap.add_argument("--scored-only", action="store_true")
    args = ap.parse_args()
    prog = fill(args.backend, args.scored_only)
    print(json.dumps(prog, indent=1))
    if args.cut:
        env = dict(os.environ, MOOT_ERAG_V3_CACHE_ONLY="1")
        subprocess.run([sys.executable, "-m", "moot.bench_erag.cut", BACKENDS[args.backend][1]], cwd=ROOT, env=env, check=True)
        subprocess.run([sys.executable, "eval/eval_erag.py"], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
