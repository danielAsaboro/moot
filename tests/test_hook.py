"""The gate in front of coding agents: an edit to a file governed by a dead decision is blocked with the evidence path, an edit
to an ungoverned file passes untouched. Integration: needs FalkorDB."""
import io
import json

import pytest

from moot import hook
from moot.graph import connect, seed

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def cfg():
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    g = db.select_graph("moot_test_hook")
    seed(g, fresh=True)
    yield dict(graph="moot_test_hook", paths={"services/uploads/*": ["D01"], "auth/keys/*": ["D06"], "infra/*.tf": ["D27"]})
    g.delete()


def run(cfg, monkeypatch, tool, path, capsys):
    monkeypatch.setattr(hook, "load", lambda path=None: cfg)
    code = hook.hook_cli(io.StringIO(json.dumps(dict(tool_name=tool, tool_input=dict(file_path=path)))))
    return code, capsys.readouterr()


def test_an_edit_under_a_dead_decision_is_blocked_with_the_path(cfg, monkeypatch, capsys):
    code, out = run(cfg, monkeypatch, "Edit", "services/uploads/limits.py", capsys)
    assert code == 2 and "DENY D01" in out.err and "PR-412" in out.err
    assert "ask Kwame Boateng" in out.err  # the owner left; the gate routes to whoever was next up her reporting line


def test_ungoverned_files_and_reads_pass(cfg, monkeypatch, capsys):
    assert run(cfg, monkeypatch, "Edit", "README.md", capsys)[0] == 0
    assert run(cfg, monkeypatch, "Read", "services/uploads/limits.py", capsys)[0] == 0


def test_gate_paths_reports_every_governing_decision(cfg, monkeypatch, capsys):
    monkeypatch.setattr(hook, "load", lambda path=None: cfg)
    rows = hook.gate_files(["services/uploads/a.py", "infra/main.tf"], cfg, "2026-10-16")
    assert {r["decision"]: r["gate"] for r in rows}["D01"] == "DENY"
    assert {r["decision"] for r in rows} == {"D01", "D27"}
