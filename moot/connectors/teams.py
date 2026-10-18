"""Teams and projects: who answers for a decision today, read from what the organisation publishes about itself.

Two sources, both git files with history, so every edge is dated:
  Kubernetes   kubernetes/community sigs.yaml. Each SIG is a Team; its chairs and tech leads LEAD it for the window they
               appear in the file (sampled at the first commit of every quarter since 2018, so windows are dated to the
               quarter); emeritus leads are the people who left that seat. Each subproject is a Project the SIG RUNS.
               A KEP's owning SIG is RESPONSIBLE_FOR it.
  CODEOWNERS   a repository's .github/CODEOWNERS (or CODEOWNERS, docs/CODEOWNERS). Each @org/team is a Team, each owned path
               a Project it RUNS, dated by the commit that added the line. A team is RESPONSIBLE_FOR a decision when the
               last CODEOWNERS rule matching the ADR's own file names it (GitHub's last-match rule).
Nothing is guessed: a decision no team is named for has no RESPONSIBLE_FOR edge.
"""
from __future__ import annotations

import fnmatch
import re
import subprocess
from datetime import date
from pathlib import Path

import yaml


def _git(d: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True, errors="replace").stdout


def _show(d: Path, spec: str) -> str:
    return subprocess.run(["git", "-C", str(d), "cat-file", "-p", spec], capture_output=True, text=True, errors="replace").stdout


def quarters(start: str, end: str) -> list[str]:
    y, m = int(start[:4]), 1
    out = []
    while f"{y:04d}-{m:02d}-01" <= end:
        out.append(f"{y:04d}-{m:02d}-01")
        m += 3
        if m > 12:
            y, m = y + 1, 1
    return out


def _load_sigs(text: str) -> dict:
    """sigs.yaml at some commits has a stray tab; YAML forbids tabs in indentation, so read it with tabs as spaces."""
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError:
        try:
            return yaml.safe_load(text.replace("\t", "  ")) or {}
        except yaml.YAMLError:
            return {}


def _seats(community: Path, rev: str, sigs: list[str] | None, cache: dict) -> set:
    if rev not in cache:
        y = _load_sigs(_show(community, f"{rev}:sigs.yaml"))
        cache[rev] = {(str(p.get("github", "")).lower(), s["dir"], role) for s in y.get("sigs", []) if sigs is None or s.get("dir") in sigs
                      for role in ("chairs", "tech_leads") for p in (s.get("leadership") or {}).get(role) or [] if p.get("github")}
    return cache[rev]


def _first(commits: list[tuple[str, str]], lo: int, hi: int, test) -> int:
    """The first index in (lo, hi] where test(sha) is true, given false at lo and true at hi (bisection over commits)."""
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if test(commits[mid][1]):
            hi = mid
        else:
            lo = mid
    return hi


def k8s_sigs(community: Path, sigs: list[str] | None, today: str | None = None, since: str = "2018-01-01",
             exact: bool = True) -> tuple[list[dict], list[dict]]:
    """Team, Project and LEADS from sigs.yaml and its history. Returns (nodes, edges).

    exact=True (the default since 2026-10-21): each seat's start and end are dated to the commit that changed sigs.yaml,
    found by bisecting the commits between quarterly samples. exact=False dates them to the quarter, as the graph K1 was
    frozen against did."""
    today = today or date.today().isoformat()
    seen: dict[tuple, list[str]] = {}  # (person, sig, role) -> quarters present
    names: dict[str, str] = {}
    head = None
    samples = quarters(since, today) + [today]
    tip = next((r for r in (_git(community, "rev-parse", "--verify", "-q", ref).strip() for ref in ("refs/heads/master", "refs/heads/main"))
                if r), "HEAD")
    for q in samples:
        rev = _git(community, "rev-list", "-1", f"--before={q}T23:59:59", tip).strip()
        if not rev:
            continue
        y = _load_sigs(_show(community, f"{rev}:sigs.yaml"))
        if not y:
            continue
        for s in y.get("sigs", []):
            if sigs is not None and s.get("dir") not in sigs:
                continue
            if q == today:
                head = head or {}
                head[s["dir"]] = s
            for role in ("chairs", "tech_leads"):
                for p in (s.get("leadership") or {}).get(role) or []:
                    gh = str(p.get("github", "")).lower()
                    if gh:
                        names[gh] = p.get("name") or gh
                        seen.setdefault((gh, s["dir"], role), []).append(q)
    nodes, edges = [], []
    for sig, s in (head or {}).items():
        tid = f"team_{sig}"
        nodes.append(dict(label="Team", id=tid, props=dict(name=f"SIG {s.get('name', sig)}", source="kubernetes/community sigs.yaml",
                                                         mission=(s.get("mission_statement") or "").strip()[:300])))
        for sp in s.get("subprojects") or []:
            pid = f"proj_{sig}_{re.sub(r'[^a-z0-9]+', '-', sp['name'].lower())}"
            nodes.append(dict(label="Project", id=pid, props=dict(name=sp["name"], description=(sp.get("description") or "").strip()[:200])))
            edges.append(dict(src=tid, rel="RUNS", dst=pid, props={}))
        for p in (s.get("leadership") or {}).get("emeritus_leads") or []:
            names.setdefault(str(p.get("github", "")).lower(), p.get("name") or p.get("github"))
    # exact dating: bisect the sigs.yaml commits between the sample where a seat appears or disappears and the one before
    commits = [tuple(l.split()[::-1]) for l in _git(community, "log", "--reverse", "--format=%H %cs", tip, "--", "sigs.yaml").splitlines()]
    index = {sha: i for i, (_, sha) in enumerate(commits)}
    at_sample = {q: _git(community, "rev-list", "-1", f"--before={q}T23:59:59", tip, "--", "sigs.yaml").strip() for q in samples}
    cache: dict = {}
    # one LEADS edge per person and team (the graph merges edges between the same pair): the span they held any seat, the
    # seat they hold last, and every seat with its own window in `history`
    spans: dict[tuple, list] = {}
    for (gh, sig, role), qs in seen.items():
        last = qs[-1]
        valid_to = "" if last == today else next((q for q in samples if q > last), today)
        valid_from = qs[0]
        if exact and commits:
            key = (gh, sig, role)
            has = lambda sha: key in _seats(community, sha, sigs, cache)
            first_rev = at_sample.get(qs[0])
            prev = next((q for q in reversed(samples) if q < qs[0]), None)
            if first_rev in index:
                lo = index.get(at_sample.get(prev), -1) if prev else -1
                i = _first(commits, lo, index[first_rev], has) if lo < index[first_rev] else index[first_rev]
                valid_from = commits[i][0] if lo >= 0 or i > 0 else valid_from
            if valid_to:
                last_rev, gone_rev = at_sample.get(last), at_sample.get(valid_to) if valid_to in at_sample else None
                if last_rev in index and gone_rev in index and index[gone_rev] > index[last_rev]:
                    j = _first(commits, index[last_rev], index[gone_rev], lambda sha: not has(sha))
                    valid_to = commits[j][0]
        spans.setdefault((gh, sig), []).append((valid_from, valid_to, role.rstrip("s").replace("_", " ")))
    for (gh, sig), ws in spans.items():
        ws.sort()
        current = [w for w in ws if not w[1]]
        role = (current or ws)[-1][2]
        edges.append(dict(src=f"u_{gh}", rel="LEADS", dst=f"team_{sig}",
                          props=dict(role=role, valid_from=ws[0][0], valid_to="" if current else max(w[1] for w in ws),
                                     history="; ".join(f"{r} {a}..{b or 'now'}" for a, b, r in ws))))
        nodes.append(dict(label="Person", id=f"u_{gh}", props=dict(name=names.get(gh, gh), role=f"SIG {role}", joined="", left="")))
    return nodes, edges


def codeowners(repo_dir: Path, org_repo: str) -> list[tuple[str, list[str], str]]:
    """[(pattern, [@owners], date the line was added)] in file order."""
    for path in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
        txt = _show(repo_dir, f"HEAD:{path}")
        if txt:
            break
    else:
        return []
    blame = _git(repo_dir, "blame", "--line-porcelain", "HEAD", "--", path)
    dates, cur = [], None
    for line in blame.splitlines():
        if line.startswith("committer-time "):
            cur = date.fromtimestamp(int(line.split()[1])).isoformat()
        elif line.startswith("\t"):
            dates.append(cur or "")
    out = []
    for i, line in enumerate(txt.splitlines()):
        s = line.split("#", 1)[0].strip()
        if not s:
            continue
        pat, *owners = s.split()
        out.append((pat, [o for o in owners if o.startswith("@")], dates[i] if i < len(dates) else ""))
    return out


def _matches(pattern: str, path: str) -> bool:
    p = pattern.lstrip("/")
    if p.endswith("/"):
        return path.startswith(p) if pattern.startswith("/") else (("/" + path).find("/" + p) >= 0)
    rx = fnmatch.translate(p.replace("**/", "*")) if "*" in p else None
    if rx:
        return bool(re.match(rx, path)) or bool(re.match(rx, path.split("/")[-1]))
    return path == p or path.startswith(p + "/") or path.endswith("/" + p)


def codeowners_teams(repo_dir: Path, org_repo: str, decisions: list[dict]) -> tuple[list[dict], list[dict]]:
    """Team / Project / RUNS from CODEOWNERS, and RESPONSIBLE_FOR where the last matching rule names a team for the ADR file."""
    rules = codeowners(repo_dir, org_repo)
    nodes, edges, teams = [], [], {}
    for pat, owners, added in rules:
        if pat in ("*", "/*"):
            continue
        pid = f"proj_{re.sub(r'[^a-z0-9]+', '-', pat.lower()).strip('-')}"
        nodes.append(dict(label="Project", id=pid, props=dict(name=pat, description=f"{org_repo} {pat}")))
        for o in owners:
            tid = f"team_{o.lstrip('@').lower().replace('/', '_')}"
            teams[tid] = o
            edges.append(dict(src=tid, rel="RUNS", dst=pid, props=dict(valid_from=added)))
    for tid, o in teams.items():
        nodes.append(dict(label="Team", id=tid, props=dict(name=o.lstrip("@"), source=f"{org_repo} CODEOWNERS", mission="")))
    for d in decisions:
        last = None
        for pat, owners, added in rules:
            if _matches(pat, d["file"]):
                last = (owners, added)
        for o in (last[0] if last else []):
            edges.append(dict(src=f"team_{o.lstrip('@').lower().replace('/', '_')}", rel="RESPONSIBLE_FOR", dst=d["id"],
                              props=dict(valid_from=max(last[1] or d["decided_on"], d["decided_on"]))))
    return nodes, edges
