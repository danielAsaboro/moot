# Moot in front of coding agents and pull requests

Which decisions govern which files is declared once, in `.moot/paths.json`, the way CODEOWNERS declares reviewers:

```json
{"graph": "larkspur", "paths": {"services/uploads/*": ["D01"], "infra/*.tf": ["D27", "D09"]}}
```

## Claude Code: block an edit that a dead decision governs

`moot hook` is a `PreToolUse` hook. For `Edit`, `Write` and `MultiEdit` on a governed file it runs the gate on each governing
decision. On **DENY** it exits 2, which blocks the edit and hands the agent the evidence path and who to ask; an **ALLOW** that
carries warnings (the product policy: nothing on record vouches for the reason) lets the edit through with the warning and who
to ask; anything else passes untouched. Add to `.claude/settings.json`:

```json
{"hooks": {"PreToolUse": [{"matcher": "Edit|Write|MultiEdit",
  "hooks": [{"type": "command", "command": "python3 -m moot.cli hook"}]}]}}
```

What the agent sees when it tries to edit `services/uploads/limits.py` in Larkspur:

```
Moot: this file is governed by a decision whose reason is dead. Re-open the decision before changing what it governs, or ask its owner.
DENY D01 (Cap file uploads at 10 MB) governs services/uploads/limits.py
  - "The API gateway enforces a 10 MB request body limit" was contradicted on 2026-03-02 by PR-412.
```

## A pull-request check

`moot gate-paths <files>` prints the gate for every decision governing the files and exits 1 on a DENY.
[examples/moot-gate.yml](examples/moot-gate.yml) runs it on a pull request's changed files.

Both are the same read-only `check_action` the API (`GET /api/gate/{id}`) and the MCP server serve; neither writes to the graph.
Tested in `tests/test_hook.py`.

## Drafting the fix

`moot draft-pr owner/repo <decision>` writes the pull request a maintainer would open for a decision Moot calls MOOT or
DISPUTED in an ingested repository: a patch (`git apply`-able) that puts a dated "under review" note under the ADR's status,
naming the reason that broke and the evidence, and a PR body that is the re-open memo with the suggested owner. Nothing is
pushed or opened. For log4brains' Lerna decision the note reads: *Under review (2026-10-21): this decision rests on "Yarn and
Lerna are considered a good practice…", which src:20241217-switch-back-to-github-flow contradicted on 2024-12-17.*
