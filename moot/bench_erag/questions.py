"""Two readers for the questions file. The blind side may only call load_blind.

load_blind asks pyarrow for two columns, so the answer key never enters the process's memory on that path.
load_gold is for scoring (eval/eval_erag.py, oracle.py) and nothing on the blind side imports it.
"""
from __future__ import annotations

from pathlib import Path

from moot.bench_erag import DATA

BLIND_COLUMNS = ("question_id", "question")
GOLD_FIELDS = ("expected_doc_ids", "gold_answer", "answer_facts")


def load_blind(path: Path | None = None) -> list[dict]:
    import pyarrow.parquet as pq
    t = pq.read_table(path or DATA / "questions.parquet", columns=list(BLIND_COLUMNS)).to_pylist()
    return sorted(t, key=lambda r: r["question_id"])


def load_gold(path: Path | None = None) -> dict[str, dict]:
    import pyarrow.parquet as pq
    return {r["question_id"]: r for r in pq.read_table(path or DATA / "questions.parquet").to_pylist()}
