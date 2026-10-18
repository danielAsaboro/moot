"""Check the unwritten reasons behind real public ADRs against public data, then build a graph for them.

  moot realworld            fetch, check, write data/realworld/checks.json and data/realworld/graph.json
  moot seed --graph public_adrs --file data/realworld/graph.json

Three checks per tool, each a dated Evidence node that SUPPORTS or CONTRADICTS a premise:
  maintained    GitHub: the default branch has a commit in the last 365 days and the repo is not archived
  open source   GitHub license (SPDX) is OSI-approved; a source-available license in the LICENSE file contradicts
  no known vuln OSV.dev: no advisory affects the tool's latest published version
A check that cannot be answered (no package, rate limit, unknown license) writes no edge and is counted as unchecked.
Set GITHUB_TOKEN to lift GitHub's 60-requests-an-hour anonymous limit. Responses are cached in data/realworld/.cache.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .records import RECORDS, RETIREMENTS, TOOLS, raw_url, source_url

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "realworld"
CACHE = OUT / ".cache"

OSI = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MPL-2.0", "GPL-2.0", "GPL-3.0", "LGPL-2.1", "LGPL-3.0",
       "AGPL-3.0", "EPL-2.0", "Unlicense", "0BSD", "GPL-2.0-only", "GPL-3.0-only", "AGPL-3.0-only", "AGPL-3.0-or-later"}
SOURCE_AVAILABLE = {"Business Source License": "BUSL-1.1", "Server Side Public License": "SSPL-1.0",
                    "Elastic License": "Elastic-2.0", "Redis Source Available License": "RSALv2"}
OSI_NAMES = {"GNU AFFERO GENERAL PUBLIC LICENSE": "AGPL-3.0", "Apache License": "Apache-2.0", "MIT License": "MIT"}


def _get(url: str, data: dict | None = None, raw: bool = False):
    key = hashlib.sha1((url + json.dumps(data or {})).encode()).hexdigest()
    f = CACHE / key
    if f.exists():
        body = f.read_bytes()
    else:
        headers = {"User-Agent": "moot-realworld"}
        if "api.github.com" in url and os.getenv("GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
        req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, headers=headers)
        if data:
            req.add_header("content-type", "application/json")
        body = urllib.request.urlopen(req, timeout=30).read()
        CACHE.mkdir(parents=True, exist_ok=True)
        f.write_bytes(body)
    return body.decode() if raw else json.loads(body)


def latest_version(eco: str, name: str) -> tuple[str, str] | None:
    """(version, published) from the package registry."""
    if eco == "npm":
        d = _get(f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='@')}")
        v = d["dist-tags"]["latest"]
        return v, d["time"][v][:10]
    if eco == "Go":
        d = _get(f"https://proxy.golang.org/{name}/@latest")
        return d["Version"], d["Time"][:10]
    if eco == "RubyGems":
        d = _get(f"https://rubygems.org/api/v1/gems/{name}.json")
        return d["version"], (d.get("version_created_at") or "")[:10]
    if eco == "Maven":
        g, a = name.split(":")
        d = _get(f"https://search.maven.org/solrsearch/select?q=g:{g}+AND+a:{a}&rows=1&wt=json")
        doc = d["response"]["docs"][0]
        return doc["latestVersion"], datetime.fromtimestamp(doc["timestamp"] / 1000, timezone.utc).date().isoformat()
    return None


def check_tool(tid: str, today: str, spec: tuple | None = None) -> dict:
    """spec: (display name, GitHub repo, OSV package or None); defaults to records.TOOLS[tid]."""
    name, repo, pkg = spec or TOOLS[tid]
    out = dict(tool=tid, name=name, repo=repo, package=list(pkg) if pkg else None, checked_on=today, checks={})
    try:
        meta = _get(f"https://api.github.com/repos/{repo}")
        commits = _get(f"https://api.github.com/repos/{repo}/commits?per_page=1&sha={meta['default_branch']}")
        last = commits[0]["commit"]["committer"]["date"][:10]
        stale = date.fromisoformat(last) < date.fromisoformat(today) - timedelta(days=365)
        out["checks"]["maintained"] = dict(
            holds=not (meta.get("archived") or stale), last_commit=last, archived=bool(meta.get("archived")), stars=meta.get("stargazers_count"),
            detail=("archived on GitHub" if meta.get("archived") else f"last commit to {meta['default_branch']} on {last}"))
        spdx = (meta.get("license") or {}).get("spdx_id")
        if spdx in OSI:
            out["checks"]["open_source"] = dict(holds=True, license=spdx, detail=f"GitHub reports {spdx}")
        else:
            text = ""
            for fn in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"):
                try:
                    text = _get(f"https://raw.githubusercontent.com/{repo}/{meta['default_branch']}/{fn}", raw=True)
                    break
                except Exception:
                    continue
            found_sa = sorted(v for k, v in SOURCE_AVAILABLE.items() if k.lower() in text.lower())
            found_osi = sorted(v for k, v in OSI_NAMES.items() if k.lower() in text.lower())
            if found_sa and found_osi:
                out["checks"]["open_source"] = dict(holds=True, license=" / ".join(found_sa + found_osi),
                                                    detail=f"offered under {', '.join(found_sa + found_osi)}; the OSI option ({', '.join(found_osi)}) keeps it open source")
            elif found_sa:
                out["checks"]["open_source"] = dict(holds=False, license=" / ".join(found_sa), detail=f"source-available: {', '.join(found_sa)}")
            elif found_osi:
                out["checks"]["open_source"] = dict(holds=True, license=found_osi[0], detail=f"LICENSE file is {found_osi[0]}")
            else:
                out["unchecked"] = out.get("unchecked", []) + [f"license: GitHub reports {spdx or 'none'} and the LICENSE file did not match a known license"]
    except Exception as ex:
        out["unchecked"] = out.get("unchecked", []) + [f"GitHub: {ex}"]
    if pkg:
        try:
            lv = latest_version(*pkg)
            if lv and pkg[0] == "Go":
                # The Go module proxy only knows versions that match the module path. Several projects tag v2+
                # releases without a /v2 module path, so the proxy's "latest" is years old. Cross-check with
                # the project's own latest GitHub release and refuse to answer when they disagree.
                try:
                    rel = _get(f"https://api.github.com/repos/{repo}/releases/latest")["tag_name"]
                except Exception:
                    rel = None
                major = lambda v: v.lstrip("v").split(".")[0]
                if not rel or major(rel) != major(lv[0]) or rel.lstrip("v").split("+")[0] != lv[0].lstrip("v").split("+")[0] and rel.lstrip("v") > lv[0].lstrip("v"):
                    out["unchecked"] = out.get("unchecked", []) + [
                        f"vulnerabilities: the Go module's latest version ({lv[0]}) does not match the project's latest release ({rel or 'unknown'})"]
                    lv = None
            if lv:
                v, published = lv
                vulns = _get("https://api.osv.dev/v1/query", {"package": {"ecosystem": pkg[0], "name": pkg[1]}, "version": v}).get("vulns", [])
                out["checks"]["no_known_vuln"] = dict(holds=not vulns, version=v, published=published, advisories=[x["id"] for x in vulns][:10],
                                                      detail=(f"{len(vulns)} OSV advisor{'y affects' if len(vulns) == 1 else 'ies affect'} {v}" if vulns else f"no OSV advisory affects {v}"))
        except Exception as ex:
            out["unchecked"] = out.get("unchecked", []) + [f"OSV: {ex}"]
    else:
        out["unchecked"] = out.get("unchecked", []) + ["vulnerabilities: no package in an OSV ecosystem"]
    return out


PREMISE = {"maintained": "{name} is actively maintained", "open_source": "{name} is open source",
           "no_known_vuln": "The current release of {name} has no known vulnerability"}
SOURCE = {"maintained": "GitHub activity", "open_source": "GitHub license", "no_known_vuln": "OSV.dev"}
# which `unchecked` notes (by prefix) explain a missing check
UNCHECKED_BY = {"maintained": ("GitHub:",), "open_source": ("license:", "GitHub:"), "no_known_vuln": ("vulnerabilities:", "OSV:")}


def unchecked_reason(t: dict, k: str) -> str:
    notes = [u.split(":", 1)[1].strip() for u in t.get("unchecked", []) if u.startswith(UNCHECKED_BY[k])]
    return "; ".join(notes) or "no check was run"


def check_retirements(records: list[dict]) -> list[str]:
    """Attach each record's retirement (records.RETIREMENTS) after verifying its quote in the retiring file. Returns ids that failed."""
    failed = []
    for r in records:
        if r["id"] not in RETIREMENTS:
            continue
        eid, repo, fn, title, d, quote, commit = RETIREMENTS[r["id"]]
        if quote not in _get(raw_url(repo, fn), raw=True):
            failed.append(r["id"])
            continue
        r["retired"] = dict(id=eid, title=title, date=d, url=source_url(repo, fn), quote=quote,
                            commit=f"https://github.com/{repo}/commit/{commit}")
    return failed


def build(records: list[dict], tools: dict[str, dict]) -> dict:
    nodes, edges = [], []
    for tid, t in tools.items():
        for k in PREMISE:
            pid = f"p_{tid}_{k}"
            c = t["checks"].get(k)
            if c is None:
                # a check nobody could answer still names a reason the decision rests on; it carries no evidence
                # either way, so the audit reports it as unchecked and the gate will not let an agent act on it
                nodes.append(dict(label="Premise", id=pid, props=dict(text=PREMISE[k].format(name=t["name"]), kind="unwritten", tool=tid, check=k,
                                                                     unchecked=unchecked_reason(t, k))))
                continue
            nodes.append(dict(label="Premise", id=pid, props=dict(text=PREMISE[k].format(name=t["name"]), kind="unwritten", tool=tid, check=k)))
            eid = f"{k}:{tid}"
            nodes.append(dict(label="Evidence", id=eid, props=dict(kind="check", title=f"{SOURCE[k]}: {c['detail']}", date=t["checked_on"],
                                                                     excerpt=c["detail"], path=f"https://github.com/{t['repo']}")))
            edges.append(dict(src=eid, rel="SUPPORTS" if c["holds"] else "CONTRADICTS", dst=pid, props=dict(at=t["checked_on"], quote=c["detail"])))
    for r in records:
        nodes.append(dict(label="Decision", id=r["id"], props=dict(title=r["title"], summary=r["quote"], decided_on=r["date"], source=r["url"],
                                                                     repo=r["repo"], status=r["status"] or "accepted")))
        sid = f"src:{r['id']}"
        nodes.append(dict(label="Evidence", id=sid, props=dict(kind="adr", title=f"{r['repo']}: {r['title']}", date=r["date"], path=r["url"], excerpt=r["quote"])))
        edges.append(dict(src=r["id"], rel="RECORDED_IN", dst=sid, props={}))
        if r.get("retired"):
            x = r["retired"]
            nodes.append(dict(label="Evidence", id=x["id"], props=dict(kind="adr", title=x["title"], date=x["date"], path=x["url"], excerpt=x["quote"])))
            edges.append(dict(src=x["id"], rel="RETIRES", dst=r["id"], props=dict(at=x["date"], quote=x["quote"])))
        for tid in r["tools"]:
            for k in PREMISE:
                edges.append(dict(src=r["id"], rel="BECAUSE_OF", dst=f"p_{tid}_{k}", props=dict(quote=PREMISE[k].format(name=tools[tid]["name"]))))
    return dict(nodes=nodes, edges=edges)


def main() -> None:
    today = date.today().isoformat()
    OUT.mkdir(parents=True, exist_ok=True)
    records, missing = [], []
    for rid, repo, fn, title, d, tool_ids, quote, status in RECORDS:
        text = _get(raw_url(repo, fn), raw=True)
        if quote not in text:  # same rule as the extractor: no quote, no record
            missing.append(rid)
            continue
        records.append(dict(id=rid, repo=repo, file=fn, url=source_url(repo, fn), title=title, date=d, tools=tool_ids, quote=quote, status=status))
    retire_failed = check_retirements(records)
    tools = {tid: check_tool(tid, today) for tid in sorted({t for r in records for t in r["tools"]})}
    checks = [c for t in tools.values() for c in t["checks"].values()]
    summary = dict(checked_on=today, records=len(records), repos=len({r["repo"] for r in records}), tools=len(tools), checks=len(checks),
                   failing=sum(1 for c in checks if not c["holds"]), unchecked=sum(len(t.get("unchecked", [])) for t in tools.values()),
                   retired=sum(1 for r in records if r.get("retired")), dropped_records=missing, dropped_retirements=retire_failed)
    (OUT / "checks.json").write_text(json.dumps(dict(summary=summary, records=records, tools=tools), indent=1))
    (OUT / "graph.json").write_text(json.dumps(build(records, tools), indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
