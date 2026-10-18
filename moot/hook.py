"""Put the gate in front of coding agents and pull requests: before a file is edited, ask Moot about the decisions that govern it.

Which decisions govern which files is declared in `.moot/paths.json` (glob -> decision ids, optionally a graph), the way
CODEOWNERS declares who reviews them. Then:

  moot gate-paths a.py b.tf        every decision governing those files, gated (ALLOW / REVALIDATE / DENY); exit 1 on a DENY
                                   (what a CI check or a pre-commit hook runs)
  moot hook                        a Claude Code PreToolUse hook: reads the tool call on stdin; for Edit, Write and MultiEdit
                                   on a governed file it gates the decisions; on DENY it exits 2 with the evidence path, which
                                   blocks the edit and tells the agent why; on REVALIDATE it lets the edit through with a note

The gate is the same read-only check_action the API and MCP serve. Nothing here writes to the graph.
"""
from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import Path

from . import tools
from .graph import graph

CONFIG = Path(".moot/paths.json")
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def load(path: Path = CONFIG) -> dict:
    """{"graph": name or null, "paths": {glob: [decision ids]}}"""
    if not path.exists():
        return dict(graph=None, paths={})
    return json.loads(path.read_text())


def governing(files: list[str], cfg: dict) -> dict[str, list[str]]:
    """decision id -> the files it governs, from the globs (matched against the path and against the path relative to cwd)."""
    out: dict[str, list[str]] = {}
    for f in files:
        rel = str(Path(f).resolve().relative_to(Path.cwd())) if Path(f).is_absolute() and str(Path(f).resolve()).startswith(str(Path.cwd())) else f
        for pattern, ids in cfg.get("paths", {}).items():
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(f, pattern):
                for d in ids:
                    out.setdefault(d, []).append(rel)
    return out


def gate_files(files: list[str], cfg: dict, as_of: str | None = None) -> list[dict]:
    g = graph(cfg.get("graph"))
    rows = []
    for did, fs in sorted(governing(files, cfg).items()):
        a = tools.check_action(g, did, as_of)
        rows.append(dict(decision=did, title=a.get("title"), gate=a["gate"], files=sorted(set(fs)),
                         reasons=[r["text"] for r in a.get("reasons", [])][:3]))
    return rows


def explain(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        lines.append(f"{r['gate']} {r['decision']} ({r['title']}) governs {', '.join(r['files'])}")
        lines += [f"  - {x}" for x in r["reasons"]]
    return "\n".join(lines)


def gate_paths_cli(files: list[str]) -> int:
    rows = gate_files(files, load())
    print(explain(rows) if rows else "no decision governs these files")
    return 1 if any(r["gate"] == "DENY" for r in rows) else 0


def hook_cli(stdin=sys.stdin) -> int:
    """Claude Code PreToolUse: exit 2 blocks the call and feeds stderr back to the agent."""
    try:
        call = json.load(stdin)
    except json.JSONDecodeError:
        return 0
    if call.get("tool_name") not in EDIT_TOOLS:
        return 0
    inp = call.get("tool_input") or {}
    f = inp.get("file_path") or inp.get("notebook_path")
    if not f:
        return 0
    rows = gate_files([f], load())
    if any(r["gate"] == "DENY" for r in rows):
        print("Moot: this file is governed by a decision whose reason is dead. Re-open the decision before changing what it "
              "governs, or ask its owner.\n" + explain(rows), file=sys.stderr)
        return 2
    if rows:
        print("Moot: " + explain(rows))
    return 0
