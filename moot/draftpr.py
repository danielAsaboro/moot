"""Draft the fix: for a decision Moot calls MOOT or DISPUTED in an ingested repository, write the pull request a maintainer
would open: a patch that marks the ADR as under review, with the reason that broke and the dated evidence, and a PR body
that is the re-open memo. Nothing is pushed or opened; the files are for a human (or an agent, after a human approves) to use.

  moot draft-pr thomvaill/log4brains 20200925-multi-packages-architecture-in-a-monorepo-with-yarn-and-lerna
      -> drafts/<owner>__<repo>/<decision>.patch and .md

The patch is a unified diff against the ADR at the repository's HEAD (git apply-able in a clone); the note goes right
under the Status heading, or at the top when the ADR has none.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

from . import tools
from .connectors import github as gh
from .graph import graph

OUT = Path("drafts")


def note(memo: dict) -> str:
    b = memo["broken"][0]
    e = b["evidence"]
    more = f" (and {len(memo['broken']) - 1} more)" if len(memo["broken"]) > 1 else ""
    return (f"Under review ({memo['as_of']}): this decision rests on \"{b['premise']['text']}\", which {e['id']} contradicted on "
            f"{e['at']}{more}. Moot verdict: {memo['verdict']}. See the pull request for the evidence path.")


def patch_for(text: str, path: str, line: str) -> str:
    lines = text.splitlines(keepends=True)
    at = next((i + 1 for i, l in enumerate(lines) if re.match(r"^#+\s*status\s*$", l.strip(), re.I)), None)
    if at is None:
        at = next((i + 1 for i, l in enumerate(lines) if re.match(r"^[-*]?\s*\**status\**\s*:", l.strip(), re.I)), 0)
        while at and at < len(lines) and re.match(r"^\s*[-*] ", lines[at]):  # past the rest of a "- Status: / - Date:" list
            at += 1
    new = lines[:at] + ["\n", f"> {line}\n"] + lines[at:]
    return "".join(difflib.unified_diff(lines, new, f"a/{path}", f"b/{path}"))


def draft(repo: str, decision_id: str, as_of: str | None = None) -> dict:
    g = graph(gh.graph_name(repo))
    memo = tools.reopen_memo(g, decision_id, as_of)
    if not memo.get("found"):
        raise SystemExit(f"no decision {decision_id} in {gh.graph_name(repo)}")
    if not memo["broken"]:
        raise SystemExit(f"{decision_id} is {memo['verdict']}: no reason has broken, nothing to draft")
    src = g.ro_query("MATCH (d:Decision {id: $id}) RETURN d.source", {"id": decision_id}).result_set[0][0]
    path = src.split("/blob/", 1)[1].split("/", 1)[1]
    text = gh.git(gh.clone(repo), "show", f"HEAD:{path}")
    out = OUT / repo.replace("/", "__")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{decision_id}.patch").write_text(patch_for(text, path, note(memo)))
    body = f"## Re-open {decision_id}\n\n" + memo["text"] + f"\n\n---\nDrafted by Moot from graph `{gh.graph_name(repo)}`. Every id above is a node in that graph; nothing was pushed."
    (out / f"{decision_id}.md").write_text(body + "\n")
    return dict(patch=str(out / f"{decision_id}.patch"), body=str(out / f"{decision_id}.md"), verdict=memo["verdict"], path=path)
