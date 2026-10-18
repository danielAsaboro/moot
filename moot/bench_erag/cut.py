"""The blind pipeline end to end, and the context every arm answers from.

  python -m moot.bench_erag.cut        rules-v1 (frozen headline): FalkorDB `erag` -> erag-data/blind_cut.json
  python -m moot.bench_erag.cut v2     rules-v2 (post-hoc):        FalkorDB `erag_v2` -> erag-data/blind_cut_v2.json
  python -m moot.bench_erag.cut v3     local-LLM claims (post-hoc): FalkorDB `erag_v3` -> erag-data/blind_cut_v3.json
  python -m moot.bench_erag.cut v3-groq  v3 on Groq (post-hoc):    FalkorDB `erag_v3_groq` -> erag-data/blind_cut_v3_groq.json

The cut: drop every top-10 document the graph proves superseded, backfill from the same BM25 ranking (never
re-admitting a dropped document), keep exactly TOP_K. Nothing here imports the answer key.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

from moot.bench_erag import DATA, TOP_K, extract, graph, pools
from moot.bench_erag.corpus import Corpus

OUT = DATA / "blind_cut.json"
VERSIONS = {"v1": ("moot.bench_erag.extract", graph.GRAPH, OUT),
            "v2": ("moot.bench_erag.extract_v2", graph.GRAPH + "_v2", DATA / "blind_cut_v2.json"),
            "v3": ("moot.bench_erag.extract_v3", graph.GRAPH + "_v3", DATA / "blind_cut_v3.json"),
            "v3-groq": ("moot.bench_erag.extract_v3_groq", graph.GRAPH + "_v3_groq", DATA / "blind_cut_v3_groq.json")}
LLM = ("v3", "v3-groq")


def fill(ranking: list[str], drop: set[str], k: int = TOP_K) -> list[str]:
    """The first k of the ranking that are not dropped. With nothing dropped this is the baseline."""
    return [d for d in ranking if d not in drop][:k]


def extractor_hash(module=extract) -> str:
    return hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()


def run(version: str = "v1") -> dict:
    mod_name, gname, out_path = VERSIONS[version]
    ex = importlib.import_module(mod_name)
    covered = None
    if version in LLM and os.getenv("MOOT_ERAG_V3_CACHE_ONLY"):
        # cut from the model responses already on disk; a question the model never saw is left uncut and listed
        model_ask, covered = ex.ask, []

        def ask(prompt: str) -> dict:
            path = ex.cache_path(prompt) if hasattr(ex, "cache_path") else \
                ex.CACHE / f"{hashlib.sha256((ex.MODEL + chr(10) + prompt).encode()).hexdigest()}.json"
            if not path.exists():
                raise LookupError(path.name)
            return model_ask(prompt)
        ex.ask = ask
    p = pools.load()
    c = Corpus()
    t0 = time.time()
    all_edges = {}
    for qid, row in p.items():
        docs = {d: c.doc(d).content for d in row["ranking"]}
        if version in LLM:
            print(f"\r{qid}", end="", file=sys.stderr, flush=True)
        try:
            all_edges[qid] = [asdict(e) for e in ex.edges(row["question"], docs)]
            if covered is not None:
                covered.append(qid)
        except LookupError:
            all_edges[qid] = []
    t_extract = time.time() - t0
    stats = graph.write(p, all_edges, gname)
    out = {}
    for qid, row in p.items():
        cut = graph.superseded(qid, gname)
        drop = {r["old_doc"] for r in cut}
        out[qid] = dict(baseline=row["ranking"][:TOP_K], moot=fill(row["ranking"], drop), dropped=sorted(drop),
                        dropped_in_top10=[d for d in row["ranking"][:TOP_K] if d in drop], proof=cut)
    payload = dict(extractor=ex.EXTRACTOR_VERSION, extractor_sha256=extractor_hash(ex), graph=gname,
                   graph_stats=stats, extract_seconds=round(t_extract, 1), questions=out)
    if covered is not None:
        payload["covered"] = covered
    if hasattr(ex, "MODEL"):
        payload["model"] = ex.MODEL
    if version == "v3-groq":
        payload["extractor_v3_sha256"] = extractor_hash(importlib.import_module("moot.bench_erag.extract_v3"))
    if version in ("v2",) + LLM:
        payload["extractor_v1_sha256"] = extractor_hash(extract)   # v2 imports v1's rules
    out_path.write_text(json.dumps(payload, indent=1))
    return payload


if __name__ == "__main__":
    r = run(sys.argv[1] if len(sys.argv) > 1 else "v1")
    q = r["questions"]
    print(r["graph_stats"], f"extract {r['extract_seconds']}s",
          "questions with a top-10 drop:", sum(1 for v in q.values() if v["dropped_in_top10"]),
          "docs dropped from top-10:", sum(len(v["dropped_in_top10"]) for v in q.values()))
