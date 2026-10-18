"""The router on ordinary questions the keyword rules get wrong ("Who owns billing?"), replaying the model's recorded tool
calls (eval/router/llm_cache.jsonl), so it runs offline. Integration: needs FalkorDB, skipped when none is reachable."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from moot.graph import connect

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def replayed(tmp_path_factory):
    try:
        connect().connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    out = tmp_path_factory.mktemp("router")
    env = {k: v for k, v in os.environ.items() if not k.startswith("MOOT_LLM")}
    subprocess.run([sys.executable, str(ROOT / "eval" / "eval_router.py")], cwd=ROOT, env=dict(env, MOOT_EVAL_OUT=str(out)),
                   check=True, capture_output=True)
    return json.loads((out / "results_router.json").read_text())


def test_the_rules_misroute_every_question_in_the_set(replayed):
    rows = [r for r in replayed["rows"] if r["split"] == "misrouted"]
    assert len(rows) >= 20 and not any(r["rules"]["right"] for r in rows)


def test_a_tool_call_routes_them_and_keeps_the_rest(replayed):
    s = replayed["summary"]
    assert s["misrouted"]["model"] >= s["misrouted"]["n"] - 3
    assert s["control"]["model"] >= s["control"]["n"] - 2
    assert all(r["model"]["by"] == "model" for r in replayed["rows"] if r["split"] == "misrouted" and r["model"]["right"])


def test_replay_reproduces_the_committed_result(replayed):
    assert replayed == json.loads((ROOT / "eval" / "results_router.json").read_text())


def test_who_owns_billing(replayed):
    r = next(r for r in replayed["rows"] if r["q"] == "Who owns billing?")
    assert r["rules"]["tool"] is None and (r["model"]["tool"], r["model"]["input"]) == ("ledger", {"system": "Billing"})
