"""Connector: any public GitHub repository's ADR folder and the pull requests behind it, as a new named graph, audited.

  moot ingest-github owner/repo [--path docs/adr] [--no-checks]

What it reads (a blob-less git clone in data/github/.repos, plus the GitHub REST API for pull requests and tool checks;
set GITHUB_TOKEN, or be logged in with `gh`, to lift the 60-requests-an-hour limit):
  the ADR folder     found in the repository tree (docs/adr, docs/decisions, doc/architecture/decisions, ...), or --path
  each ADR           title, own date, status line (the backtest's parser, moot/backtest/labels.py), "superseded by" links
  its history        `git log --follow` on the file, so renames keep their authors: the first author owns the decision,
                     every author knows why it was made
  its pull requests  the PR that introduced the ADR (RECORDED_IN, AUTHORED by whoever opened it) and, for an ADR its
                     repository later marked superseded or deprecated, the PR that changed the status (RETIRES, dated);
                     a PR is found from the squash subject "(#123)" or the first merge commit after the change
  the tools it picks named in its title (the backtest's catalogue, moot/backtest/tools.py), each checked like the public
                     ADRs: maintained (GitHub), open source (licence), no known vulnerability (OSV), as dated Evidence

What it writes: data/github/<owner>__<repo>/graph.json and summary.json, then MERGEs the graph into FalkorDB as
`gh_<owner>_<repo>`. An ADR that states no reason Moot can check (no tool in its title) is UNDOCUMENTED, not guessed.
A status-change date is the last commit to the file, so it is never earlier than the change itself.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

from ..backtest.labels import OWN_DATE, PAT, SKIP, classify, status_text, title_of
from ..backtest.tools import TOOLS as TITLE_TOOLS
from ..realworld import check as rw
from ..realworld.records import TOOLS as RW_TOOLS

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "github"
# The backtest's title catalogue, plus the public-ADR tools matched by name: tool id -> (name, title regex, GitHub repo)
CATALOGUE = dict(TITLE_TOOLS)
for _tid, (_name, _repo, _pkg) in RW_TOOLS.items():
    CATALOGUE.setdefault(_tid, (_name, r"\b" + re.escape(_name.split(" (")[0]) + r"\b", _repo))
CATALOGUE.update(msw=("Mock Service Worker", r"\bmsw\b|mock service worker", "mswjs/msw"))
ADR_DIRS = re.compile(r"(^|/)(adrs?|decisions|decision-records?|architecture[-_]decisions?|architecture[-_]decision[-_]records?|"
                      r"architecture/decisions|design-decisions)$", re.I)


def token() -> str | None:
    if os.getenv("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    if shutil.which("gh"):
        r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            os.environ["GITHUB_TOKEN"] = r.stdout.strip()  # realworld.check reads it too
            return os.environ["GITHUB_TOKEN"]
    return None


def api(path: str):
    return rw._get("https://api.github.com/" + path)  # cached in data/realworld/.cache, token from GITHUB_TOKEN


def graph_name(full: str) -> str:
    return "gh_" + re.sub(r"[^a-z0-9]+", "_", full.lower()).strip("_")


def clone(full: str) -> Path:
    d = OUT / ".repos" / full.replace("/", "__")
    if d.exists():
        subprocess.run(["git", "-C", str(d), "fetch", "-q", "--filter=blob:none", "origin", "+HEAD:HEAD"], capture_output=True, timeout=900)
    else:
        d.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--bare", "--filter=blob:none", "--single-branch", f"https://github.com/{full}", str(d)],
                       check=True, timeout=1800)
    return d


def git(d: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True, errors="replace").stdout


def find_adrs(d: Path, path: str | None) -> tuple[str, list[str]]:
    files = [f for f in git(d, "ls-tree", "-r", "--name-only", "HEAD").splitlines() if f.lower().endswith(".md")]
    if path:
        path = path.strip("/")
        return path, sorted(f for f in files if os.path.dirname(f) == path and not SKIP.search(f))
    by_dir: dict[str, list[str]] = {}
    for f in files:
        d = os.path.dirname(f)
        if (ADR_DIRS.search(d) or PAT.search(f)) and not SKIP.search(f) and re.match(r"^\d|^adr", os.path.basename(f), re.I):
            by_dir.setdefault(d, []).append(f)
    if not by_dir:
        return "", []
    best = max(by_dir, key=lambda d: (len(by_dir[d]), bool(ADR_DIRS.search(d))))
    return best, sorted(by_dir[best])


PR_SUBJECT = re.compile(r"Merge pull request #(\d+)|\(#(\d+)\)\s*$")


def pr_number(d: Path, sha: str, subject: str) -> int | None:
    m = PR_SUBJECT.search(subject)
    if m:
        return int(m.group(1) or m.group(2))
    merges = git(d, "log", "--merges", "--ancestry-path", "--reverse", "--format=%s", f"{sha}..HEAD").splitlines()
    m = PR_SUBJECT.search(merges[0]) if merges else None
    return int(m.group(1) or m.group(2)) if m else None


def pr_for(full: str, d: Path, c: dict) -> dict | None:
    n = pr_number(d, c["sha"], c["subject"])
    if n is None:  # rebased or fast-forwarded: ask GitHub which merged PR carried the commit
        try:
            n = next((p["number"] for p in api(f"repos/{full}/commits/{c['sha']}/pulls") if p.get("merged_at")), None)
        except Exception:
            n = None
    if n is None:
        return None
    try:
        pr = api(f"repos/{full}/pulls/{n}")
        return dict(id=f"pr:{n}", title=pr["title"], date=(pr.get("merged_at") or pr["created_at"])[:10], author=pr["user"]["login"],
                    url=pr["html_url"], excerpt=(pr.get("body") or "").strip()[:300])
    except Exception:  # rate-limited or not a PR: keep what git knows
        return dict(id=f"pr:{n}", title=c["subject"], date=c["date"], author=c["author"], url=f"https://github.com/{full}/pull/{n}", excerpt="")


LOGINS: dict[str, str] = {}   # git author name -> GitHub login, so a commit author and a PR author are one Person
NAMES: dict[str, str] = {}    # GitHub login -> the name git knows them by


def learn_login(full: str, c: dict) -> None:
    if c["author"] in LOGINS:
        return
    try:
        login = (api(f"repos/{full}/commits/{c['sha']}").get("author") or {}).get("login")
    except Exception:
        login = None
    LOGINS[c["author"]] = login or ""
    if login:
        NAMES.setdefault(login, c["author"])


def pid(who: str) -> str:
    login = LOGINS.get(who) or who
    return "gh:" + (re.sub(r"[^a-z0-9]+", "-", login.lower()).strip("-") or "unknown")


def person(who: str) -> dict:
    login = LOGINS.get(who) or (who if who in NAMES else "")
    return dict(label="Person", id=pid(who), props=dict(name=NAMES.get(login, who), role="contributor", joined="", left="", login=login))


def history(d: Path, f: str) -> list[dict]:
    """Commits to the file, newest first, following renames."""
    out = []
    for line in git(d, "log", "--follow", "--format=%H%x09%cs%x09%an%x09%s", "HEAD", "--", f).splitlines():
        sha, day, author, subject = (line.split("\t", 3) + ["", "", "", ""])[:4]
        out.append(dict(sha=sha, date=day, author=author, subject=subject))
    return out


def number_of(fn: str) -> str | None:
    m = re.match(r"^(?:adr[-_ ]?)?0*(\d{1,4})(?!\d)", os.path.basename(fn), re.I)
    return m.group(1) if m else None


def successor_of(status: str, decisions: dict[str, dict], by_num: dict[str, dict], me: str) -> dict | None:
    """The ADR a "superseded by" status points at: a link to its file first, then an ADR number."""
    for target in re.findall(r"\(([^)\s]+?\.md)(?:#[^)]*)?\)", status):
        x = decisions.get(os.path.splitext(os.path.basename(target))[0])
        if x and x["id"] != me:
            return x
    for n in re.findall(r"(?:adr|decision|record)?[-_ #]*0*(\d{1,4})(?!\d)", status, re.I):
        if n in by_num and by_num[n]["id"] != me:
            return by_num[n]
    return None


def summary_of(txt: str) -> str:
    m = re.search(r"^#+\s*decision[^\n]*\n+(.+?)(?:\n#|\Z)", txt, re.I | re.S | re.M)
    body = (m.group(1) if m else txt).strip()
    return re.sub(r"\s+", " ", re.sub(r"[#*>`_]|\[([^\]]*)\]\([^)]*\)", r"\1", body))[:300]


def ingest(full: str, path: str | None = None, checks: bool = True, today: str | None = None) -> dict:
    today = today or date.today().isoformat()
    token()
    repo_dir = clone(full)
    ref = git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD").strip() or "HEAD"
    folder, files = find_adrs(repo_dir, path)
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    add = lambda n: nodes.setdefault(n["id"], n)
    decisions, by_num = [], {}
    if not files:
        raise SystemExit(f"no ADR folder found in {full}; pass --path")
    for f in files:
        txt = git(repo_dir, "show", f"HEAD:{f}")
        st = status_text(txt)
        cls = classify(st)
        if cls in ("proposed", "rejected"):
            continue  # never in force
        commits = history(repo_dir, f)
        if not commits:
            continue
        first, last = commits[-1], commits[0]
        own = OWN_DATE.search(txt[:3000])
        decided = own.group(1) if own and own.group(1) <= first["date"] else first["date"]
        did = os.path.splitext(os.path.basename(f))[0]
        url = f"https://github.com/{full}/blob/{ref}/{f}"
        for c in commits:
            learn_login(full, c)
        authors = list(dict.fromkeys(c["author"] for c in reversed(commits) if c["author"]))
        d = dict(id=did, file=f, url=url, title=title_of(txt, f), decided_on=decided, status=st or "accepted", cls=cls,
                 last_commit=last["date"], last=last, first=first, authors=authors, text=txt)
        decisions.append(d)
        if number_of(f):
            by_num[number_of(f)] = d
    for d in decisions:
        add(dict(label="Decision", id=d["id"], props=dict(title=d["title"], summary=summary_of(d["text"]), decided_on=d["decided_on"],
                                                         source=d["url"], repo=full, status=d["status"][:120])))
        src = f"src:{d['id']}"
        add(dict(label="Evidence", id=src, props=dict(kind="adr", title=f"{full}: {d['title']}", date=d["decided_on"], path=d["url"],
                                                    excerpt=summary_of(d["text"]))))
        edges.append(dict(src=d["id"], rel="RECORDED_IN", dst=src, props={}))
        for name in d["authors"]:
            add(person(name))
            edges.append(dict(src=pid(name), rel="AUTHORED", dst=src, props={}))
        if d["authors"]:
            edges.append(dict(src=pid(d["authors"][0]), rel="OWNS", dst=d["id"], props=dict(valid_from=d["decided_on"], valid_to="", handed_over_from="")))
        intro = pr_for(full, repo_dir, d["first"])
        if intro:
            add(dict(label="Evidence", id=intro["id"], props=dict(kind="pr", title=intro["title"], date=intro["date"], path=intro["url"], excerpt=intro["excerpt"])))
            add(person(intro["author"]))
            edges += [dict(src=d["id"], rel="RECORDED_IN", dst=intro["id"], props={}),
                      dict(src=pid(intro["author"]), rel="AUTHORED", dst=intro["id"], props={})]
        if d["cls"] == "dead":
            succ = successor_of(d["status"], {x["id"]: x for x in decisions}, by_num, d["id"])
            if succ and succ["decided_on"] <= d["last_commit"]:
                edges.append(dict(src=succ["id"], rel="SUPERSEDES", dst=d["id"], props=dict(at=d["last_commit"], quote=d["status"][:200])))
            else:
                change = pr_for(full, repo_dir, d["last"]) if d["last"]["sha"] != d["first"]["sha"] else None
                eid = change["id"] if change else f"status:{d['id']}"
                add(dict(label="Evidence", id=eid, props=dict(kind="pr" if change else "adr",
                                                              title=change["title"] if change else f"{d['title']}: status changed to {d['status'][:80]}",
                                                              date=d["last_commit"], path=change["url"] if change else d["url"],
                                                              excerpt=d["status"][:300])))
                if change:
                    add(person(change["author"]))
                    edges.append(dict(src=pid(change["author"]), rel="AUTHORED", dst=eid, props={}))
                edges.append(dict(src=eid, rel="RETIRES", dst=d["id"], props=dict(at=d["last_commit"], quote=d["status"][:200])))
    tools_used: dict[str, list[str]] = {}
    for d in decisions:
        for tid, (_, rx, _) in CATALOGUE.items():
            if re.search(rx, d["title"], re.I):
                tools_used.setdefault(tid, []).append(d["id"])
    tool_checks = {}
    if checks:
        for tid in sorted(tools_used):
            name, _, trepo = CATALOGUE[tid]
            pkg = RW_TOOLS[tid][2] if tid in RW_TOOLS else None
            tool_checks[tid] = rw.check_tool(tid, today, (name, trepo, pkg))
        sub = rw.build([], tool_checks)  # Premise + dated check Evidence per tool, as for the public ADRs
        for n in sub["nodes"]:
            add(n)
        edges += sub["edges"]
        for tid, dids in tools_used.items():
            for did in dids:
                for k in rw.PREMISE:
                    edges.append(dict(src=did, rel="BECAUSE_OF", dst=f"p_{tid}_{k}", props=dict(quote=rw.PREMISE[k].format(name=CATALOGUE[tid][0]))))
    payload = dict(nodes=list(nodes.values()), edges=edges)
    out = OUT / full.replace("/", "__")
    out.mkdir(parents=True, exist_ok=True)
    (out / "graph.json").write_text(json.dumps(payload, indent=1))
    summary = dict(repo=full, graph=graph_name(full), folder=folder, read_on=today, adr_files=len(files), decisions=len(decisions),
                   retired=sum(1 for d in decisions if d["cls"] == "dead"), people=sum(1 for n in nodes.values() if n["label"] == "Person"),
                   pull_requests=sum(1 for n in nodes.values() if n["id"].startswith("pr:")), tools=sorted(tools_used),
                   checks=sum(len(t["checks"]) for t in tool_checks.values()),
                   failing=sum(1 for t in tool_checks.values() for c in t["checks"].values() if not c["holds"]))
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def summary_for_graph(name: str) -> dict | None:
    for f in OUT.glob("*/summary.json"):
        s = json.loads(f.read_text())
        if s.get("graph") == name:
            return s
    return None


def ingested() -> list[str]:
    """Repositories with a committed snapshot in data/github, as owner/name."""
    return sorted(json.loads(f.read_text())["repo"] for f in OUT.glob("*/summary.json"))


def load(full: str) -> Path:
    return OUT / full.replace("/", "__") / "graph.json"


def audit(full: str, fresh: bool = True) -> dict:
    """Seed the repository's graph into FalkorDB and audit every decision with the agent gate."""
    from ..graph import graph, seed
    from .. import tools
    g = graph(graph_name(full))
    seed(g, load(full), fresh=fresh)
    s = json.loads((load(full).parent / "summary.json").read_text())
    rows = tools.ledger(g, s["read_on"], 4)
    gates = {r["id"]: tools.check_action(g, r["id"], s["read_on"])["gate"] for r in rows}
    count = lambda xs: {k: sum(1 for x in xs if x == k) for k in sorted(set(xs))}
    s.update(verdicts=count([r["verdict"] for r in rows]), gates=count(list(gates.values())),
             moot=[dict(id=r["id"], title=r["title"]) for r in rows if r["verdict"] == "MOOT"])
    (load(full).parent / "summary.json").write_text(json.dumps(s, indent=1))
    return s
