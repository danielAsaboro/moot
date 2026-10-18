"""The second answer key: did the repository's own code drop the library the decision picked?

For each decision the gate denied, read its repository's dependency manifests (package.json, go.mod,
Gemfile, pyproject.toml, requirements; up to three folders deep) when the decision was made and at HEAD.
Present at HEAD means the code still depends on the tool the gate flagged. Written to data/backtest/code.json
and shown next to each flag in eval/results_backtest.md.
"""
from __future__ import annotations

import json
import re
import subprocess

from .labels import OUT, REPOS_DIR, git
from .tools import DEPENDENCY, MANIFESTS


BASENAMES = {m.rsplit("/", 1)[-1] for m in MANIFESTS}


def manifests_at(repo, rev: str) -> dict[str, str]:
    """Every dependency manifest up to three folders deep (monorepos keep one per package)."""
    names = [p for p in git(repo, "ls-tree", "-r", "--name-only", rev).splitlines()
             if p.rsplit("/", 1)[-1] in BASENAMES and p.count("/") <= 3 and not re.search(r"node_modules|fixture|test|example", p)]
    if not names:
        return {}
    blob = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"], capture_output=True,
                          input="".join(f"{rev}:{p}\n" for p in names).encode()).stdout
    out, pos = {}, 0
    for p in names:
        nl = blob.index(b"\n", pos)
        hdr = blob[pos:nl].decode(errors="replace")
        pos = nl + 1
        if hdr.endswith("missing"):
            continue
        size = int(hdr.split()[-1])
        out[p] = blob[pos:pos + size].decode("utf-8", "replace")
        pos += size + 1
    return out


def first_rev_on_or_after(repo, day: str) -> str | None:
    h = git(repo, "rev-list", "-1", f"--before={day}T23:59:59", "HEAD").strip()
    return h or None


def main() -> None:
    gates = json.loads((OUT / "gates.json").read_text())
    denied = {i for i, s in gates.items() if any(x["gate"] == "DENY" for x in s)}
    decisions = [d for d in json.loads((OUT / "decisions.json").read_text()) if d["id"] in denied]
    out = {}
    for d in decisions:
        for t in d["tools"]:
            if t not in DEPENDENCY:
                continue
            repo = REPOS_DIR / d["repo"].replace("/", "__")
            rx = re.compile(DEPENDENCY[t])
            head = manifests_at(repo, "HEAD")
            at_birth_rev = first_rev_on_or_after(repo, max(d["born"], d["first_commit"]))
            at_birth = manifests_at(repo, at_birth_rev) if at_birth_rev else {}
            row = dict(decision=d["id"], tool=t, manifests=sorted(head), at_head=any(rx.search(x) for x in head.values()),
                       at_decision=any(rx.search(x) for x in at_birth.values()))
            out[f"{d['id']}|{t}"] = row
    (OUT / "code.json").write_text(json.dumps(out, indent=1))
    rows = list(out.values())
    seen = [r for r in rows if r["at_decision"]]
    print(f"{len(rows)} denied decision-library pairs; {len(seen)} visible in a manifest when decided; "
          f"{sum(1 for r in rows if r['at_head'])} still in the code at HEAD")


if __name__ == "__main__":
    main()
