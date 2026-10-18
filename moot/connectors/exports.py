"""Connectors for exports a team already has on disk: a Slack workspace export and an issue tracker's export. No API key,
no network: the files are read, turned into dated Evidence, and merged into an existing graph.

  moot ingest-slack  <export dir> --graph G     Slack's standard export: users.json, channels.json, <channel>/<day>.json
  moot ingest-issues <file.json>  --graph G     `gh issue list --json number,title,state,author,createdAt,closedAt,body,url,labels`
                                                (repo given with --repo), or a Jira export ({"issues": [{key, fields: ...}]})

Every message and issue becomes an Evidence node (kind chat or ticket) with its date, AUTHORED by its writer, and
MENTIONS every decision of the graph it names by id (KEP-3130, D01, ADR 7 for an ADR numbered 0007). MENTIONS is where a
decision was discussed; it never changes a verdict (only dated SUPPORTS / CONTRADICTS / SUPERSEDES / RETIRES do).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from falkordb import Graph

ID_TOKEN = re.compile(r"\b(?:KEP-\d+|[A-Z]\d{2,3}|ADR[- ]?\d+)\b", re.I)


def _day(ts) -> str:
    if isinstance(ts, (int, float)) or (isinstance(ts, str) and re.fullmatch(r"\d+(\.\d+)?", ts)):
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).date().isoformat()
    return str(ts or "")[:10]


def decision_index(g: Graph) -> dict[str, str]:
    """Every way a text can name a decision of this graph -> its id: the id itself and, for numbered ADRs, 'ADR 7'."""
    out = {}
    for (did,) in g.ro_query("MATCH (d:Decision) RETURN d.id").result_set:
        out[did.lower()] = did
        m = re.match(r"(?:adr-?)?0*(\d{1,4})[-_]", did, re.I)
        if m:
            out[f"adr {int(m.group(1))}"] = did
    return out


def mentions(text: str, index: dict[str, str]) -> set[str]:
    found = set()
    for tok in ID_TOKEN.findall(text or ""):
        t = tok.lower().replace("-", " ") if tok.lower().startswith("adr") else tok.lower()
        t = re.sub(r"adr\s*0*(\d+)", lambda m: f"adr {int(m.group(1))}", t)
        if t in index:
            found.add(index[t])
    return found


def slack(export: Path, index: dict[str, str]) -> dict:
    users = {u["id"]: u for u in json.loads((export / "users.json").read_text())} if (export / "users.json").exists() else {}
    channels = [c["name"] for c in json.loads((export / "channels.json").read_text())] if (export / "channels.json").exists() \
        else sorted(p.name for p in export.iterdir() if p.is_dir())
    nodes, edges, people = [], [], {}
    for ch in channels:
        for day in sorted((export / ch).glob("*.json")):
            for m in json.loads(day.read_text()):
                if m.get("subtype") in ("channel_join", "channel_leave", "bot_message") or not m.get("text"):
                    continue
                eid = f"slack:{ch}:{m['ts']}"
                text = m["text"]
                nodes.append(dict(label="Evidence", id=eid, props=dict(kind="chat", title=f"#{ch}: {text[:60]}", date=_day(m["ts"]),
                                                                      excerpt=text[:1000], source=f"slack export #{ch}")))
                if m.get("user"):
                    u = users.get(m["user"], {})
                    pid = f"slack_{m['user']}"
                    people[pid] = u.get("real_name") or u.get("name") or m["user"]
                    edges.append(dict(src=pid, rel="AUTHORED", dst=eid, props={}))
                if m.get("thread_ts") and m["thread_ts"] != m["ts"]:
                    edges.append(dict(src=eid, rel="REPLY_TO", dst=f"slack:{ch}:{m['thread_ts']}", props={}))
                for d in mentions(text, index):
                    edges.append(dict(src=eid, rel="MENTIONS", dst=d, props=dict(at=_day(m["ts"]))))
    nodes += [dict(label="Person", id=p, props=dict(name=n)) for p, n in people.items()]
    return dict(nodes=nodes, edges=edges)


def issues(path: Path, index: dict[str, str], repo: str = "") -> dict:
    data = json.loads(path.read_text())
    rows = data.get("issues", []) if isinstance(data, dict) else data
    nodes, edges, people = [], [], {}
    for r in rows:
        if "fields" in r:  # Jira
            f = r["fields"]
            eid, title, body = f"jira:{r['key']}", f"{r['key']}: {f.get('summary', '')}", f.get("description") or ""
            state, opened, closed = (f.get("status") or {}).get("name", ""), _day(f.get("created")), _day(f.get("resolutiondate"))
            who = (f.get("reporter") or {}).get("displayName")
            pid = f"jira_{re.sub(r'[^a-z0-9]+', '_', who.lower())}" if who else None
        else:  # GitHub
            eid, title, body = f"issue:{repo}#{r['number']}", f"#{r['number']}: {r.get('title', '')}", r.get("body") or ""
            state, opened, closed = r.get("state", ""), _day(r.get("createdAt")), _day(r.get("closedAt"))
            who = (r.get("author") or {}).get("login")
            pid = f"u_{who.lower()}" if who else None
        nodes.append(dict(label="Evidence", id=eid, props=dict(kind="ticket", title=title, date=opened, closed=closed, state=state,
                                                              excerpt=body[:1000], source=r.get("url") or repo or "issue export")))
        if pid:
            people[pid] = who
            edges.append(dict(src=pid, rel="AUTHORED", dst=eid, props={}))
        for d in mentions(title + "\n" + body, index):
            edges.append(dict(src=eid, rel="MENTIONS", dst=d, props=dict(at=opened)))
    nodes += [dict(label="Person", id=p, props=dict(name=n)) for p, n in people.items()]
    return dict(nodes=nodes, edges=edges)


def merge(g: Graph, payload: dict, out: Path) -> dict:
    """Write the payload next to the graph's data and MERGE it (moot/graph.py seed: idempotent). Mentioned decisions are
    matched by id, never created; a Person already in the graph keeps its properties."""
    from ..graph import seed
    have = {r[0] for r in g.ro_query("MATCH (p:Person) RETURN p.id").result_set}
    payload["nodes"] = [n for n in payload["nodes"] if not (n["label"] == "Person" and n["id"] in have)]
    decisions = {e["dst"] for e in payload["edges"] if e["rel"] == "MENTIONS"}
    payload["nodes"] += [dict(label="Decision", id=d, props={}) for d in sorted(decisions)]  # MERGE on id: matches, adds nothing
    payload["nodes"] += [dict(label="Person", id=p, props={}) for p in sorted(have & {e["src"] for e in payload["edges"]})]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1))
    seed(g, out)
    return dict(evidence=sum(1 for n in payload["nodes"] if n["label"] == "Evidence"),
                mentions=sum(1 for e in payload["edges"] if e["rel"] == "MENTIONS"), decisions_mentioned=len(decisions))
