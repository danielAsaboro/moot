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


def k8s_sigs(community: Path, sigs: list[str] | None, today: str | None = None, since: str = "2018-01-01") -> tuple[list[dict], list[dict]]:
    """Team, Project and LEADS from sigs.yaml and its history. Returns (nodes, edges)."""
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
        try:
            y = yaml.safe_load(_show(community, f"{rev}:sigs.yaml")) or {}
        except yaml.YAMLError:
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
    # one LEADS edge per person and team (the graph merges edges between the same pair): the span they held any seat, the
    # seat they hold last, and every seat with its own window in `history`
    spans: dict[tuple, list] = {}
    for (gh, sig, role), qs in seen.items():
        last = qs[-1]
        valid_to = "" if last == today else next((q for q in samples if q > last), today)
        spans.setdefault((gh, sig), []).append((qs[0], valid_to, role.rstrip("s").replace("_", " ")))
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
