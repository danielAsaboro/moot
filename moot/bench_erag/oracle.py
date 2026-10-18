"""ORACLE arm: Canon's setup, reproduced. It reads the answer key, and is labelled ORACLE everywhere it appears.

Canon seeds its graph from research/conflict_inventory.json, whose old_doc_id/new_doc_id were picked by reading each
conflict question's gold documents and gold answer. This module takes those labels as given and applies Canon's
cut: drop the retired gold document, pin the current gold document if BM25 missed it (evicting the lowest-ranked
candidate), backfill from the same ranking, keep exactly TOP_K. It is only ever imported by the scoring side.
"""
from __future__ import annotations

import json
from pathlib import Path

from moot.bench_erag import ROOT, TOP_K

INVENTORY = Path(ROOT.parent / "canon-teardown" / "research" / "conflict_inventory.json")


def inventory(path: Path = INVENTORY) -> dict[str, dict]:
    return {c["question_id"]: c for c in json.loads(path.read_text())["conflicts"]}


def resolves(c: dict) -> bool:
    """Canon's canonize order: explicit supersession, else T1 timestamps; anything else stays CONTESTED and is not cut."""
    return bool(c.get("explicit_supersession_in_text")) or c.get("timestamp_quality") == "T1"


def oracle_context(ranking: list[str], old_doc: str, new_doc: str, pin: bool = True, k: int = TOP_K) -> list[str]:
    kept = [d for d in ranking[:k] if d != old_doc]
    if pin and new_doc not in kept:
        kept = kept[: k - 1] + [new_doc]
    for d in ranking[k:]:
        if len(kept) >= k:
            break
        if d != old_doc and d not in kept:
            kept.append(d)
    return kept[:k]
