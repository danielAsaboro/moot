"""EnterpriseRAG-Bench, blind.

A FalkorDB supersession graph built only from what BM25 retrieves for each question, never from the
benchmark's answer key. The modules split along one line:

  blind side   corpus.py · questions.load_blind · extract.py · graph.py · cut.py
               These never read expected_doc_ids, gold_answer or answer_facts (tests/test_erag.py enforces it).
  scoring side questions.load_gold · oracle.py · eval/eval_erag.py
               Only these touch the answer key, and only after the blind cut is fixed.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.getenv("MOOT_ERAG_DIR", ROOT.parent / "erag-data"))
DATASET = "onyx-dot-app/EnterpriseRAG-Bench"
REVISION = "69916e31c68aa5963c00248fd7f0bc12d04fd235"  # the revision Canon's run_manifest records
TOP_K = 10    # context budget, every arm
POOL = 50     # what the blind extractor reads per question
