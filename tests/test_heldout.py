"""Study H1's guards: the answer key is pinned, the scorer refuses a changed one, and no arm can read a status line."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from moot.heldout.gold import digest

ROOT = Path(__file__).resolve().parents[1]
GOLD = json.loads((ROOT / "eval" / "heldout" / "gold.json").read_text())
INPUTS = json.loads((ROOT / "data" / "heldout" / "inputs.json").read_text())


def test_the_gold_is_the_pinned_one():
    pinned = (ROOT / "eval" / "heldout" / "GOLD.sha256").read_text().split()[0]
    assert digest(GOLD) == GOLD["sha256"] == pinned


def test_the_scorer_refuses_a_changed_answer_key(tmp_path):
    bad = json.loads(json.dumps(GOLD))
    flip = next(u for u in bad["units"] if u["gold"] == "HOLDS")
    flip["gold"] = "DEAD"
    (tmp_path / "gold.json").write_text(json.dumps(bad))
    r = subprocess.run([sys.executable, str(ROOT / "eval" / "eval_heldout.py")], cwd=ROOT, capture_output=True, text=True,
                       env=dict(os.environ, MOOT_HELDOUT_GOLD=str(tmp_path / "gold.json"), MOOT_EVAL_OUT=str(tmp_path)))
    assert r.returncode != 0 and "refusing to score" in r.stderr
    assert not (tmp_path / "results_heldout.json").exists()


def test_every_unit_was_in_force_and_committed_on_t0():
    for u in GOLD["units"]:
        assert u["born"] <= GOLD["t0"]
        assert u["gold"] in ("DEAD", "HOLDS") and u["split"] in ("dev", "test")
        if u["gold"] == "DEAD":
            assert GOLD["t0"] < u["first"]["date"] <= GOLD["end"]


def test_no_arm_input_carries_a_status_line_or_the_key():
    status = re.compile(r"^\s*(#+\s*)?\**\s*status\s*\**\s*[:=|]?\s*$|^[-*>|\s]*\**\s*status\s*\**\s*[:=|]", re.I | re.M)
    for u in INPUTS["units"]:
        assert not status.search(u["adr"]), u["id"]
        assert set(u) == {"id", "repo", "title", "born", "tools", "path_t0", "adr"}  # nothing from gold.json beyond the unit
    for repo in INPUTS["repos"].values():
        for a in repo["adrs"].values():
            assert not status.search(a["text"])
    assert all(d["at"] <= INPUTS["t0"] for docs in INPUTS["evidence"].values() for d in docs)
    assert all(v["published"] <= INPUTS["t0"] for t in INPUTS["tools"].values() for v in t.get("osv", []))
