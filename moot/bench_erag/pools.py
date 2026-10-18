"""Per-question BM25 candidate pools (blind: question text only) -> erag-data/pools.json."""
from __future__ import annotations

import json

from moot.bench_erag import DATA, POOL
from moot.bench_erag.corpus import Corpus
from moot.bench_erag.questions import load_blind

PATH = DATA / "pools.json"


def build() -> dict[str, dict]:
    c = Corpus()
    out = {q["question_id"]: dict(question=q["question"], ranking=c.search(q["question"], POOL)) for q in load_blind()}
    PATH.write_text(json.dumps(out, indent=1))
    return out


def load() -> dict[str, dict]:
    return json.loads(PATH.read_text()) if PATH.exists() else build()


if __name__ == "__main__":
    print(len(build()), "pools ->", PATH)
