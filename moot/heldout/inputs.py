"""What each arm of study H1 may see: only what existed on T0, and never the answer key.

Per unit: the ADR's text as it stood on T0 with its Status section removed (the status is what the key reads), the other
ADRs of the same repository on T0 (titles and text, statuses removed too), and the dated evidence about each tool the
title picks, up to T0: the tool's own commit history (a gap of more than 365 days, and commits resuming), the vendor's
licence announcements, and OSV advisories published by T0 where the tool has an OSV package. Nothing dated after T0.

  python3 -m moot.heldout.inputs        -> data/heldout/inputs.json (reads eval/heldout/gold.json and data/backtest)
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

from ..backtest.labels import PAT, REPOS_DIR, SKIP, git, title_of
from ..realworld.records import TOOLS as RW_TOOLS
from .evidence import merged
from .gold import GOLD, rev_at, _read

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "heldout" / "inputs.json"
MAX_TEXT = 6000


def strip_status(txt: str) -> str:
    """Drop the Status section (heading to next heading), Status lines and front-matter status fields."""
    lines, out, skip = txt.splitlines(), [], False
    for i, l in enumerate(lines):
        s = l.strip()
        if re.match(r"^(#+\s*|\**)\s*status\s*\**\s*:?\s*$", s, re.I) or (
                re.match(r"^status\s*$", s, re.I) and i + 1 < len(lines) and re.match(r"^[-=~^*]{3,}$", lines[i + 1].strip())):
            skip = True
            continue
        if skip:
            if s.startswith("#") or (i + 1 < len(lines) and re.match(r"^[-=~^]{3,}$", lines[i + 1].strip()) and s):
                skip = False
            else:
                continue
        if re.match(r"^[-*>|\s]*\**\s*status\s*\**\s*[:=|]", s, re.I):
            continue
        out.append(l)
    return "\n".join(out).strip()


def path_at(repo: Path, path: str, rev: str) -> str | None:
    """The ADR's path on `rev`, following renames back from its path at HEAD."""
    if git(repo, "cat-file", "-t", f"{rev}:{path}").strip() == "blob":
        return path
    log = git(repo, "log", "--follow", "--name-only", "--format=@%H", "HEAD", "--", path)
    names = [l for l in log.splitlines() if l and not l.startswith("@")]
    for p in names:
        if git(repo, "cat-file", "-t", f"{rev}:{p}").strip() == "blob":
            return p
    return None


def osv(pkg: tuple[str, str] | None, t0: str) -> list[dict]:
    if not pkg:
        return []
    req = urllib.request.Request("https://api.osv.dev/v1/query", data=json.dumps({"package": {"ecosystem": pkg[0], "name": pkg[1]}}).encode(),
                                 headers={"content-type": "application/json"})
    vulns = json.loads(urllib.request.urlopen(req, timeout=60).read()).get("vulns", [])
    return sorted([dict(id=v["id"], published=v.get("published", "")[:10], summary=(v.get("summary") or "")[:160])
                   for v in vulns if v.get("published", "")[:10] and v["published"][:10] <= t0], key=lambda v: v["published"])


def evidence_docs(tools: set[str], t0: str) -> dict[str, list[dict]]:
    ev = merged()
    out = {}
    for t in sorted(tools):
        e = ev.get(t)
        if not e:
            out[t] = []
            continue
        docs = []
        for k in ("maintained", "open_source"):
            for x in e[k]:
                if x["at"] <= t0:
                    docs.append(dict(id=f"{k}:{t}:{x['at']}", tool=t, check=k, rel=x["rel"], at=x["at"],
                                     title=(f"git history of {e['repo']}: {x['quote']}" if k == "maintained" else f"{x['quote']} ({x.get('source', '')})")))
        out[t] = docs
    return out


def main(gold_path: Path = GOLD, out: Path = OUT) -> None:
    gold = json.loads(gold_path.read_text())
    t0 = gold["t0"]
    ev = merged()
    tools = {t for u in gold["units"] for t in u["tools"]}
    repos: dict[str, dict] = {}
    for repo_name in sorted({u["repo"] for u in gold["units"]}):
        repo = REPOS_DIR / repo_name.replace("/", "__")
        rev = rev_at(repo, t0)
        files = [f for f in git(repo, "ls-tree", "-r", "--name-only", rev).splitlines() if PAT.search(f) and not SKIP.search(f)]
        texts = _read(repo, rev, files)
        repos[repo_name] = dict(rev=rev, adrs={p: dict(title=title_of(t, p), text=strip_status(t)[:MAX_TEXT]) for p, t in texts.items()})
    units = []
    for u in gold["units"]:
        repo = REPOS_DIR / u["repo"].replace("/", "__")
        r = repos[u["repo"]]
        p = path_at(repo, u["path"], r["rev"])
        adr = r["adrs"].get(p) if p else None
        units.append(dict(id=u["id"], repo=u["repo"], title=u["title"], born=u["born"], tools=u["tools"], path_t0=p,
                          adr=adr["text"] if adr else ""))
    tool_info = {t: dict(name=ev[t]["name"] if t in ev else t, repo=ev[t]["repo"] if t in ev else None,
                         first_commit=ev[t]["first_commit"] if t in ev else None,
                         osv_package=list(RW_TOOLS[t][2]) if t in RW_TOOLS and RW_TOOLS[t][2] else None) for t in sorted(tools)}
    for t, info in tool_info.items():
        try:
            info["osv"] = osv(tuple(info["osv_package"]) if info["osv_package"] else None, t0)
        except Exception as ex:
            info["osv"], info["osv_error"] = [], str(ex)[:120]
    payload = dict(t0=t0, gold_sha256=gold["sha256"], units=units, tools=tool_info, evidence=evidence_docs(tools, t0),
                   repos={k: dict(rev=v["rev"], adrs=v["adrs"]) for k, v in repos.items()})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1) + "\n")
    print(f"{len(units)} units, {sum(1 for u in units if not u['adr'])} without their ADR text on T0, {len(tools)} tools, "
          f"{sum(len(v) for v in payload['evidence'].values())} evidence documents dated by {t0}")


if __name__ == "__main__":
    main()
