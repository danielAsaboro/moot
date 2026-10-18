"""The answer key: when did maintainers themselves stop standing behind a decision?

Read from the git history of the ADR folders of public repositories. Nobody on this project wrote
these labels: a decision "dies" on the date of the commit in which its own repository marked it
superseded, deprecated, invalidated (or similar), or moved it into an archive folder, or on the date
a later ADR in the same repository titled itself as replacing, removing or migrating away from the
tool the decision picked.

  python3 -m moot.backtest.labels     clone (blob-less) into data/backtest/.repos, write data/backtest/decisions.json
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "backtest"
REPOS_DIR = OUT / ".repos"

# Every public repository we found that keeps more than a handful of ADRs in git. Nothing was dropped for its outcome.
REPOS = [
    "CMSgov/easi-app", "DFE-Digital/apply-for-teacher-training", "GSA/notifications-api", "ONSdigital/eq-questionnaire-runner",
    "alphagov/content-publisher", "alphagov/govuk-aws", "alphagov/govuk-infrastructure", "alphagov/publishing-api",
    "backstage/backstage", "cloudfoundry/korifi", "edgexfoundry/edgex-docs", "guardian/dotcom-rendering",
    "home-assistant/architecture", "kyma-project/community", "ministryofjustice/cloud-platform",
    "ministryofjustice/modernisation-platform", "mozilla/fxa", "npryce/adr-tools", "openedx/course-discovery",
    "openedx/credentials", "openedx/ecommerce", "openedx/edx-enterprise", "openedx/edx-platform",
    "openedx/frontend-app-learning", "openedx/frontend-platform", "openedx/openedx-learning", "openedx/paragon",
    "operate-first/blueprint", "thomvaill/log4brains", "wmde/fundraising-application",
]

PAT = re.compile(r"(adr|decision)[^/]*/([^/]*/)?[^/]*\.(md|rst)$|(^|/)adr-?[0-9]+[^/]*\.(md|rst)$", re.I)
SKIP = re.compile(r"template|readme|index|node_modules|/_|summary|integration-tests|/example|/fixtures?/|/test", re.I)
ARCHIVE_DIR = re.compile(r"/(archive|archived|historic\w*|deprecated|superseded|obsolete|retired)/", re.I)

DEAD = re.compile(r"\b(supersed\w*|deprecat\w*|replaced|obsolete\w*|retired|abandoned|archived|withdrawn|reverted|revoked|"
                  r"overridden|outdated|invalidated|no longer)\b", re.I)
REJ = re.compile(r"\b(rejected|declined|not accepted)\b", re.I)
ACC = re.compile(r"\b(final|accepted|approved|adopted|agreed|decided|implemented|active|in effect|done|complete|completed)\b", re.I)
PROP = re.compile(r"\b(proposed|draft|in review|under review|pending|wip|open|in progress|provisional|proposal|review|incomplete|deferred)\b", re.I)
OWN_DATE = re.compile(r"(?:^|\n)\s*[-*]?\s*\**(?:date|created(?: on)?|decision date)\**\s*[:|]?\s*\**\s*(\d{4}-\d{2}-\d{2})", re.I)


def git(repo: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, errors="replace").stdout


def clone(name: str) -> Path:
    d = REPOS_DIR / name.replace("/", "__")
    if not d.exists():
        REPOS_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", "--single-branch",
                        f"https://github.com/{name}", str(d)], check=True, timeout=900)
    return d


def status_text(txt: str) -> str | None:
    lines = txt.splitlines()
    for i, l in enumerate(lines[:40]):  # | STATUS | column tables
        if l.count("|") >= 3 and re.search(r"\|\s*\**status\**\s*\|", l, re.I) and i + 2 < len(lines):
            cols = [c.strip().lower().strip("*") for c in l.strip().strip("|").split("|")]
            vals = [c.strip() for c in lines[i + 2].strip().strip("|").split("|")]
            if "status" in cols and len(vals) > cols.index("status"):
                return vals[cols.index("status")]
        m = re.match(r"^\|\s*\**status\**\s*\|\s*(.+?)\s*\|", l.strip(), re.I)
        if m:
            return m.group(1)
    for i, l in enumerate(lines[:80]):
        s = l.strip()
        m = re.match(r"^[-*>\s]*\**\s*status\s*\**\s*[:=]\s*\**(.*)$", s, re.I)  # "Status: x", "- Status: x", front matter
        if m and m.group(1).strip(" *"):
            return m.group(1).strip()
        if re.match(r"^(#+\s*|\**)\s*status\s*\**\s*:?\s*$", s, re.I) or (
                re.match(r"^status\s*$", s, re.I) and i + 1 < len(lines) and re.match(r"^[-=~^*]{3,}$", lines[i + 1].strip())):
            out = []
            for l2 in lines[i + 1:i + 15]:
                t = l2.strip()
                if re.match(r"^[-=~^*]{3,}$", t) and not out:
                    continue
                if not t:
                    if out:
                        break
                    continue
                if t.startswith("#") or (out and re.match(r"^[-=~^]{3,}$", t)):
                    break
                out.append(t)
            return " ".join(out)[:300]
    return None


def classify(st: str | None) -> str:
    if st is None:
        return "none"  # a committed ADR with no status line is a decision in force
    # templates list every option: "Proposed [Proposed, Accepted, Rejected, Deprecated, Superseded]"
    st = re.sub(r"\[[^\]]*(?:,|\|)[^\]]*\]", "", st)
    if DEAD.search(st):
        return "dead"
    if REJ.search(st):
        return "rejected"
    if ACC.search(st):
        return "accepted"
    if PROP.search(st):
        return "proposed"
    return "other"


def title_of(txt: str, path: str) -> str:
    lines = txt.splitlines()
    for l in lines[:20]:
        m = re.match(r"^#\s+(.*)", l.strip()) or re.match(r"^title\s*:\s*(.*)", l.strip(), re.I)
        if m:
            return m.group(1).strip().strip("'\"")
    for i, l in enumerate(lines[:12]):
        if l.strip() and not re.match(r"^\.\. ", l) and i + 1 < len(lines) and re.match(r"^[=#*~-]{3,}$", lines[i + 1].strip()) \
                and l.strip().lower() not in ("status", "context", "decision"):
            return l.strip()
    return os.path.basename(path)


def mine(name: str) -> list[dict]:
    repo = clone(name)
    files = [f for f in git(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines() if PAT.search(f) and not SKIP.search(f)]
    if not files:
        return []
    dirs = sorted({os.path.dirname(f) for f in files})
    log = git(repo, "log", "--reverse", "-M", "--name-status", "--format=C %H %cs", "--", *dirs)
    git(repo, "log", "-p", "--format=", "--", *dirs)  # one batched fetch of every blob we are about to read
    ident: dict[str, str] = {}
    hist: dict[str, list] = defaultdict(list)
    jobs, cur = [], None
    for line in log.splitlines():
        if line.startswith("C "):
            _, h, d = line.split(" ", 2)
            cur = (h, d)
            continue
        if not line.strip():
            continue
        parts = line.split("\t")
        if parts[0].startswith("R"):
            old, path = parts[1], parts[2]
            ident[path] = ident.get(old, old)
            if ARCHIVE_DIR.search("/" + path) and not ARCHIVE_DIR.search("/" + old):
                hist[ident[path]].append(dict(commit=cur[0], date=cur[1], path=path, archived=True))
        else:
            path = parts[1]
            ident.setdefault(path, path)
        if not (PAT.search(path) and not SKIP.search(path)):
            continue
        if parts[0] == "D":
            hist[ident[path]].append(dict(commit=cur[0], date=cur[1], path=path, deleted=True))
            continue
        jobs.append((ident[path], cur[0], cur[1], path))
    blob = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"], capture_output=True,
                          input="".join(f"{h}:{p}\n" for _, h, _, p in jobs).encode()).stdout
    pos, texts = 0, []
    for _ in jobs:
        nl = blob.index(b"\n", pos)
        hdr = blob[pos:nl].decode(errors="replace")
        pos = nl + 1
        if hdr.endswith("missing"):
            texts.append("")
            continue
        size = int(hdr.split()[-1])
        texts.append(blob[pos:pos + size].decode("utf-8", "replace"))
        pos += size + 1
    for (i, h, d, p), t in zip(jobs, texts):
        s = status_text(t)
        own = OWN_DATE.search(t[:3000])
        hist[i].append(dict(commit=h, date=d, path=p, status=s, cls=classify(s), title=title_of(t, p),
                            own_date=own.group(1) if own else None, text=t if len(hist[i]) == 0 else None))
    return [dict(repo=name, key=i, events=ev) for i, ev in hist.items() if any("cls" in e for e in ev)]


def decide(rec: dict) -> dict | None:
    """One decision: when it came into force, when (if ever) its own repository stopped standing behind it."""
    ev = sorted(rec["events"], key=lambda e: e["date"])
    live = [e for e in ev if "cls" in e]
    first = live[0]
    if first["cls"] == "rejected" or all(e["cls"] in ("proposed", "rejected", "other") for e in live):
        return None  # never in force
    start = next(e for e in live if e["cls"] not in ("proposed", "rejected"))
    born = start["date"]
    if start is first and first.get("own_date") and first["own_date"] < born:
        born = first["own_date"]  # imported ADRs carry their own date; the import commit is not when they were made
    death = None
    for e in ev:
        if e["date"] < start["date"]:
            continue
        if e.get("archived") or e.get("cls") == "dead":
            death = dict(date=e["date"], kind="archived" if e.get("archived") else "status",
                         quote=e.get("status") or f"moved to {e['path']}", commit=e["commit"], path=e["path"])
            break
    born_dead = bool(death and death["commit"] == start["commit"])
    if born_dead:  # imported already dead; keep it only if the status itself dates the death ("Invalidated on 2021-08-04")
        m = re.search(r"(\d{4}-\d{2}-\d{2})", death["quote"])
        if m and m.group(1) > born:
            death, born_dead = dict(death, date=m.group(1), kind="status (dated in text)"), False
    deleted = next((e["date"] for e in ev if e.get("deleted")), None)
    last = live[-1]
    return dict(id=f"{rec['repo']}:{os.path.basename(rec['key'])}", repo=rec["repo"], path=last["path"], title=last["title"],
                born=born, first_commit=first["date"], death=None if born_dead else death, born_dead=born_dead, deleted=deleted,
                status=last.get("status"), url=f"https://github.com/{rec['repo']}/blob/HEAD/{last['path']}")


def main() -> None:
    from .tools import NOT_PICKED, TOOLS
    out, seen = [], {}
    for name in REPOS:
        for rec in mine(name):
            d = decide(rec)
            if not d:
                continue
            k = (d["repo"], re.sub(r"\W+", " ", d["title"].lower()).strip())
            if k in seen:  # the same ADR copied to a second folder: one decision, made at the earlier date, alive while either copy is
                prev = seen[k]
                prev["born"] = min(prev["born"], d["born"])
                if prev["deleted"] and not d["deleted"]:
                    prev.update(deleted=None, path=d["path"], url=d["url"], status=d["status"], death=d["death"] or prev["death"])
                continue
            seen[k] = d
            drop = set().union(*[v for rx, v in NOT_PICKED.items() if re.search(rx, d["title"], re.I)])
            named = {t for t, (_, rx, _) in TOOLS.items() if re.search(rx, d["title"], re.I)}
            d["tools"], d["dropped"] = sorted(named - drop), sorted(named & drop)
            out.append(d)
    # A later ADR in the same repository whose title drops a tool (NOT_PICKED) kills the earlier decisions that picked it.
    for d in out:
        for t in d["tools"]:
            for later in out:
                if later["repo"] == d["repo"] and later["born"] > d["born"] and t in later["dropped"] \
                        and (not d["death"] or later["born"] < d["death"]["date"]):
                    d["death"] = dict(date=later["born"], kind="replaced", quote=later["title"], commit=None, path=later["path"])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "decisions.json").write_text(json.dumps(sorted(out, key=lambda d: d["id"]), indent=1))
    n = len(out)
    print(f"{n} decisions in force at some point; {sum(1 for d in out if d['death'])} later abandoned by their own repository; "
          f"{sum(1 for d in out if d['tools'])} name an outside tool")


if __name__ == "__main__":
    main()
