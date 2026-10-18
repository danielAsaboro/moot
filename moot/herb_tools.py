"""Read-only tools over the HERB graph (moot/connectors/herb.py) for an agent answering HERB questions.

Every tool takes the question's product and scopes every row to it. Every query is fixed Cypher sent with GRAPH.RO_QUERY
and parameters; the model only fills JSON arguments. Each call returns compact JSON (at most MAX_CHARS characters).

  GRAPH_TOOLS   search, get_artifact, resolve_entity, doc_discussion, list_issues, list_prs, links_shared, competitors,
                rank, decision_lineage, who_knows, connection_path, find_missing
  SEARCH_TOOLS  search and get_artifact only, over the same text: the arm of study X1 without the graph

Search is full-text only (FalkorDB's RediSearch index on Evidence title + excerpt); there are no embeddings in Moot.
Every tool runs fixed Cypher; the model never writes any.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict

from .connectors.herb import DIRECTION, GRAPH, norm, token_set_ratio, words
from .graph import graph as _graph

MAX_CHARS = 3000
UNRESOLVED = ("reported", "reopened")


def _g(g):
    return g if g is not None else _graph(GRAPH)


def rows(g, q: str, params: dict | None = None) -> list[dict]:
    r = _g(g).ro_query(q, params or {})
    cols = [c[1] if isinstance(c, (list, tuple)) else c for c in r.header]
    return [dict(zip(cols, row)) for row in r.result_set]


def _clip(s, n):
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


def fit(obj: dict, limit: int = MAX_CHARS) -> str:
    """JSON of obj within limit: long strings are cut first, then the longest list loses items from its end."""
    def size(o):
        return len(json.dumps(o, ensure_ascii=False, default=str))

    def strings(o, n):
        if isinstance(o, str):
            return _clip(o, n)
        if isinstance(o, list):
            return [strings(x, n) for x in o]
        if isinstance(o, dict):
            return {k: strings(v, n) for k, v in o.items()}
        return o

    out, n = obj, 1200
    while size(out) > limit and n > 120:
        out, n = strings(obj, n), int(n * 0.7)
    dropped = 0
    while size(out) > limit:
        lists = []

        def find(o, path):
            if isinstance(o, list) and len(o) > 1:
                lists.append((len(json.dumps(o, default=str)), path))
            if isinstance(o, dict):
                for k, v in o.items():
                    find(v, path + [k])
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    find(v, path + [i])
        find(out, [])
        if not lists:
            break
        _, path = max(lists)
        tgt = out
        for k in path:
            tgt = tgt[k]
        tgt.pop()
        dropped += 1
        if isinstance(out, dict):
            out["truncated"] = dropped
    return json.dumps(out, ensure_ascii=False, default=str)


def _fts(query: str) -> str:
    """A RediSearch query from free text: words OR-ed, punctuation dropped (no query syntax gets through)."""
    ws = [w for w in re.findall(r"[A-Za-z0-9]+", query or "") if len(w) > 1]
    return "|".join(ws[:24]) or "*"


def _people(g, ids) -> dict:
    ids = sorted({i for i in ids if i})
    if not ids:
        return {}
    return {r["id"]: r for r in rows(g, "MATCH (p:Person) WHERE p.id IN $ids RETURN p.id AS id, p.name AS name, p.role AS role", {"ids": ids})}


# ---------- text ----------

def search(product: str, query: str, kind: str | None = None, limit: int = 8, g=None) -> dict:
    """Full-text search over the product's artifacts (messages, docs, meetings, PRs, links). kind filters: chat, doc, meeting,
    meeting_chat, pr, link."""
    limit = max(1, min(int(limit or 8), 15))
    rs = rows(g, "CALL db.idx.fulltext.queryNodes('Evidence', $q) YIELD node, score WHERE node.product = $p AND ($kind IS NULL OR node.kind = $kind) "
                 "RETURN node.id AS id, node.kind AS kind, node.date AS date, node.author AS author, node.channel AS channel, node.title AS title, "
                 "node.excerpt AS text, node.link AS link, score ORDER BY score DESC LIMIT $k", {"q": _fts(query), "p": product, "kind": kind or None, "k": limit})
    return dict(product=product, query=query, hits=[{k: (_clip(v, 260) if k == "text" else v) for k, v in r.items() if v not in (None, "") and k != "score"} for r in rs])


def get_artifact(id: str, product: str | None = None, part: int = 0, g=None) -> dict:
    """One artifact in full (paged by part): a chat message comes with its conversation; a PR with reviews and outcome; an issue
    with its fields; a doc with its feedback; a meeting transcript in parts."""
    if str(id).startswith("iss:"):
        r = rows(g, "MATCH (i:Issue {id: $id}) RETURN properties(i) AS p", {"id": id})
        return dict(id=id, issue=r[0]["p"] if r else None)
    r = rows(g, "MATCH (e:Evidence {id: $id}) RETURN properties(e) AS p", {"id": id})
    if not r:
        return dict(id=id, found=False)
    p = dict(r[0]["p"])
    if product and p.get("product") != product:
        return dict(id=id, found=False, note="not in this product")
    text = p.pop("excerpt", "") or ""
    part = max(0, int(part or 0))
    out = dict(id=id, kind=p.get("kind"), date=p.get("date"), author=p.get("author"), title=p.get("title"), link=p.get("link"))
    if p.get("kind") == "chat":
        conv = rows(g, "MATCH (e:Evidence {product: $p}) WHERE e.conv = $c RETURN e.id AS id, e.date AS date, e.author AS author, e.excerpt AS text "
                       "ORDER BY e.date, e.id", {"p": p["product"], "c": p.get("conv")})
        at = next((i for i, m in enumerate(conv) if m["id"] == id), 0)
        lo = max(0, at - 3 + part * 12)
        out.update(channel=p.get("channel"), conversation=[dict(id=m["id"], author=m["author"], text=_clip(m["text"], 400)) for m in conv[lo:lo + 12]],
                   messages=len(conv), next_part=part + 1 if lo + 12 < len(conv) else None)
        return out
    if p.get("kind") == "pr":
        rv = rows(g, "MATCH (r:Person)-[x:REVIEWED]->(e:Evidence {id: $id}) RETURN r.id AS by, x.state AS state, x.comment AS comment, x.at AS at ORDER BY x.at", {"id": id})
        out.update({k: p.get(k) for k in ("number", "repo", "state", "merged", "approved", "outcome", "action", "reverted_by", "revert_reason", "reverts", "workstream")},
                   summary=_clip(text, 600), reviews=[dict(r, comment=_clip(r["comment"], 220)) for r in rv])
        return out
    chunk = 2200
    out.update(text=text[part * chunk:(part + 1) * chunk], next_part=part + 1 if (part + 1) * chunk < len(text) else None)
    for k in ("doc_type", "version", "feedback", "participants", "external", "channel"):
        if p.get(k) not in (None, "", []):
            out[k] = p[k] if k != "feedback" else _clip(p[k], 700)
    if p.get("kind") == "link":
        out["shared_by"] = rows(g, "MATCH (s:Person)-[x:SHARES]->(e:Evidence {id: $id}) RETURN s.id AS id, x.at AS at, x.via AS via", {"id": id})
    return out


# ---------- entities ----------

def resolve_entity(product: str, name: str | None = None, role: str | None = None, g=None) -> dict:
    """The product by name or codename; people by name (namesakes ranked by activity in the product) or by role (people active in
    the product: team members or authors of its artifacts)."""
    proj = rows(g, "MATCH (p:Project) RETURN p.id AS id, p.aliases AS aliases")
    want = norm(name or product)
    match = [p for p in proj if norm(p["id"]) == want or want in [norm(a) for a in p["aliases"] or []]]
    out = dict(product=product, project=match[0] if match else None)
    q = ("MATCH (p:Person) WHERE ($name IS NULL OR toLower(p.name) = toLower($name)) AND ($role IS NULL OR toLower(p.role) = toLower($role)) "
         "OPTIONAL MATCH (p)-[:AUTHORED]->(e:Evidence {product: $p}) WITH p, count(e) AS acts "
         "OPTIONAL MATCH (p)-[m:MEMBER_OF]->(:Project {id: $p}) WITH p, acts, count(m) AS member "
         "WHERE acts > 0 OR member > 0 OR ($name IS NOT NULL AND $role IS NULL) "
         "RETURN p.id AS id, p.name AS name, p.role AS role, acts AS artifacts, member > 0 AS team_member ORDER BY acts DESC, p.id LIMIT 40")
    if role or (name and not match):
        out["people"] = rows(g, q, {"name": name if name and not match else None, "role": role or None, "p": product})
        if name and not match:
            out["customers"] = rows(g, "MATCH (c:Customer)-[:WORKS_AT]->(co:Company) WHERE toLower(c.name) = toLower($n) OR toLower(co.name) = toLower($n) OR c.id = $n "
                                       "RETURN c.id AS id, c.name AS name, co.name AS company LIMIT 20", {"n": name})
    return out


# ---------- documents ----------

def _doc_types(g, product):
    return rows(g, "MATCH (d:Evidence {product: $p, kind: 'doc'}) RETURN d.id AS id, d.doc_type AS type, d.version AS version, d.date AS date, d.author AS author, "
                   "d.feedback AS feedback, d.link AS link ORDER BY d.date", {"p": product})


def doc_discussion(product: str, doc_type: str, role: str | None = None, g=None) -> dict:
    """Who said what about one document type: the Slack conversation each version's share opens, split into feedback from
    others (with their role) and the author's replies;
    plus the doc's recorded feedback and meetings held on that doc type with what each speaker said. role filters feedback."""
    docs = [d for d in _doc_types(g, product) if norm(d["type"]) == norm(doc_type) or norm(doc_type) in norm(d["type"])]
    if not docs:
        return dict(product=product, doc_type=doc_type, found=False, types=sorted({d["type"] for d in _doc_types(g, product)}))
    shares = rows(g, "MATCH (m:Evidence {product: $p, kind: 'chat'})-[:LINKS_TO]->(d:Evidence) WHERE d.id IN $ids "
                     "RETURN m.id AS id, m.date AS date, m.conv AS conv, m.author AS author, d.id AS doc ORDER BY m.date", {"p": product, "ids": [d["id"] for d in docs]})
    feedback, replies, authors = [], [], {d["author"] for d in docs if d["author"]}
    seen = set()
    for s in shares:  # the conversation each share opens
        if s["conv"] in seen:
            continue
        seen.add(s["conv"])
        msgs = rows(g, "MATCH (m:Evidence {product: $p, kind: 'chat'}) WHERE m.conv = $c RETURN m.id AS id, m.author AS author, m.date AS date, m.excerpt AS text "
                       "ORDER BY m.date", {"p": product, "c": s["conv"]})
        authors.add(s["author"])
        for m in msgs:
            (replies if m["author"] in authors else feedback).append(dict(m, doc=s["doc"]))
    ppl = _people(g, [m["author"] for m in feedback + replies] + list(authors))
    for m in feedback + replies:
        m["role"] = ppl.get(m["author"], {}).get("role", "")
    if role:
        feedback = [m for m in feedback if norm(m["role"]) == norm(role)]
    meetings = rows(g, "MATCH (t:Evidence {product: $p, kind: 'meeting'}) WHERE toLower(t.doc_type) = toLower($t) RETURN t.id AS id, t.date AS date, t.excerpt AS text, "
                       "t.participants AS participants", {"p": product, "t": docs[0]["type"]})
    mt = []
    for t in meetings:
        speakers = {r["id"]: r for r in rows(g, "MATCH (p:Person)-[:SPOKE_IN]->(t:Evidence {id: $id}) RETURN p.id AS id, p.name AS name, p.role AS role", {"id": t["id"]})}
        by_name = {v["name"]: v for v in speakers.values()}
        lines = []
        for line in t["text"].splitlines():
            nm, _, said = line.partition(": ")
            sp = by_name.get(nm)
            if sp and said and (not role or norm(sp["role"]) == norm(role)):
                lines.append(dict(by=sp["id"], role=sp["role"], said=_clip(said, 220)))
        mt.append(dict(id=t["id"], date=t["date"], speakers=sorted(speakers), lines=lines[:12]))
    return dict(product=product, doc_type=docs[0]["type"],
                versions=[dict(id=d["id"], version=d["version"], date=d["date"], author=d["author"]) for d in docs],
                authors=sorted(a for a in authors if a), reviewers=sorted({m["author"] for m in feedback}),
                feedback=[dict(id=m["id"], by=m["author"], role=m["role"], text=_clip(m["text"], 330)) for m in feedback],
                recorded_feedback=[_clip(d["feedback"], 500) for d in docs if d["feedback"]],
                author_replies=len(replies), meetings=mt)


# ---------- issues ----------

def _issues(g, product, status=None, company=None, component=None, person=None):
    rs = rows(g, "MATCH (i:Issue {product: $p}) OPTIONAL MATCH (i)-[:REPORTED_BY]->(c:Customer)-[:WORKS_AT]->(co:Company) "
                 "RETURN i.id AS id, i.title AS title, i.status AS status, i.component AS component, i.customer AS customer, co.name AS company, "
                 "i.assignee AS assignee, i.resolved_by AS resolved_by, i.dismissed_by AS dismissed_by, i.fix_pr AS fix_pr, i.reopened AS reopened, "
                 "i.reopened_after AS reopened_after, i.opened AS opened, i.description AS description ORDER BY i.opened", {"p": product})
    st = (status or "").lower()
    if st in ("unresolved", "open", "active"):
        rs = [r for r in rs if r["status"] in UNRESOLVED]
    elif st in ("no_fix_needed", "not_a_bug", "dismissed"):
        rs = [r for r in rs if r["dismissed_by"]] if st != "dismissed" else [r for r in rs if r["status"] == "dismissed"]
    elif st == "ever_dismissed":
        rs = [r for r in rs if r["dismissed_by"]]
    elif st:
        rs = [r for r in rs if r["status"] == st]
    if company:
        rs = [r for r in rs if r["company"] and norm(r["company"]) == norm(company)]
    if component:
        cw = words(component)
        rs = [r for r in rs if r["component"] and (norm(component) in norm(r["component"]) or token_set_ratio(component, r["component"]) >= 80
                                                   or len(cw & words(r["component"])) >= max(1, len(cw) // 2))]
    if person:
        rs = [r for r in rs if person in (r["assignee"], r["resolved_by"], r["dismissed_by"])]
    return rs


def list_issues(product: str, status: str | None = None, company: str | None = None, component: str | None = None, person: str | None = None, g=None) -> dict:
    """Customer issues from the bug channels with their current status (reported, resolved, dismissed = no fix needed, reopened;
    'unresolved' = reported or reopened; 'ever_dismissed' = dismissed at some point), company, component, assignee, who resolved
    or dismissed it and the fix PR. Counts by status and company come with it."""
    rs = _issues(g, product, status, company, component, person)
    all_ = _issues(g, product)
    return dict(product=product, filter=dict(status=status, company=company, component=component, person=person),
                counts_by_status=dict(Counter(r["status"] for r in all_)), counts_by_company=dict(Counter(r["company"] for r in rs).most_common()),
                issues=[{k: (_clip(v, 160) if k == "description" else v) for k, v in r.items() if v not in (None, "", 0)} for r in rs])


# ---------- PRs ----------

def _prs(g, product):
    return rows(g, "MATCH (e:Evidence {product: $p, kind: 'pr'}) WHERE e.external = false RETURN e.id AS id, e.number AS number, e.link AS link, e.title AS title, "
                   "e.excerpt AS summary, e.author AS author, e.date AS date, e.state AS state, e.merged AS merged, e.approved AS approved, e.outcome AS outcome, "
                   "e.action AS action, e.reverted_by AS reverted_by, e.revert_reason AS revert_reason, e.reverts AS reverts, e.workstream AS ws, e.repo AS repo "
                   "ORDER BY e.repo, e.number", {"p": product})


def _ws_text(g, product, prs):
    """Text that names each workstream: its PR titles and summaries, and the planning-meeting sentences naming its owner."""
    names = _people(g, [p["author"] for p in prs])
    meet = " ".join(r["t"] for r in rows(g, "MATCH (t:Evidence {product: $p, kind: 'meeting'}) RETURN t.excerpt AS t", {"p": product}))
    sents = re.split(r"(?<=[.!?])\s+|\n", meet)
    text = defaultdict(str)
    owners = {}
    for p in prs:
        text[p["ws"]] += " " + p["title"] + " " + p["title"] + " " + (p["summary"] or "")
        owners.setdefault(p["ws"], p["author"])
    for w, eid in owners.items():
        nm = names.get(eid, {}).get("name")
        if nm:
            text[w] += " " + " ".join(s for s in sents if nm in s)
    return text


def list_prs(product: str, topic: str | None = None, status: str | None = None, author: str | None = None, g=None) -> dict:
    """The product's own PRs grouped into workstreams (re-submissions, reverts and the owner's follow-ups stay together). topic picks
    the best-matching workstream(s). status filters by outcome: to_merge (approved, open, the team still means to merge),
    to_close (approved but the team decided not to merge), reverted (reverted_direction or reverted_bugs, from the revert PR's own
    summary), revert (the revert PRs), merged, closed, open, approved, not_approved. author: an employee id. Bug-fix PRs are
    their own workstreams (fix:...) and show up with a topic or author only."""
    prs = _prs(g, product)
    if not prs:
        return dict(product=product, prs=[])
    groups = defaultdict(list)
    for p in prs:
        groups[p["ws"]].append(p)
    chosen = [w for w in groups if not w.startswith("fix:") or author]
    scores = {}
    if topic:
        text = _ws_text(g, product, prs)
        tw = words(topic)
        tf = {w: Counter(x for x in norm(text[w]).split() if x in tw) for w in chosen}
        df = Counter(x for w in chosen for x in tf[w])
        scores = {w: sum(math.log(1 + c) * math.log(1 + len(chosen) / df[x]) for x, c in tf[w].items()) for w in chosen}
        best = max(scores.values(), default=0)
        ranked = sorted(chosen, key=lambda w: -scores[w])
        chosen = [w for w in ranked[:2] if best > 0 and scores[w] >= best * 0.85]
    st = (status or "").lower()

    def keep(p):
        if author and p["author"] != author:
            return False
        if not st:
            return True
        if st in ("approved", "not_approved"):
            return bool(p["approved"]) == (st == "approved")
        if st == "reverted":
            return (p["outcome"] or "").startswith("reverted")
        return p["outcome"] == st or (st in ("reverted_direction", "product_direction") and p["outcome"] == "reverted_direction") \
            or (st in ("reverted_bugs", "introduced_bugs") and p["outcome"] == "reverted_bugs")
    out = []
    for w in sorted(chosen, key=lambda w: -scores.get(w, 0)):
        items = [dict(link=p["link"], title=_clip(p["title"], 70), outcome=p["outcome"], state=p["state"], merged=p["merged"], approved=p["approved"],
                      **({"action": p["action"]} if p["action"] else {}), **({"reverted_by": p["reverted_by"].rsplit("_", 1)[-1]} if p["reverted_by"] else {}))
                 for p in groups[w] if keep(p)]
        out.append(dict(workstream=w, owner=groups[w][0]["author"], match=round(scores.get(w, 0) / (max(scores.values()) or 1), 2) if scores else None, titles=sorted({_clip(p["title"], 60) for p in groups[w]})[:6], prs=items))
    out = [o for o in out if o["prs"] or not (st or author)]
    if not topic and not author:
        out = [dict(o, prs=o["prs"] if st else [], n=len(groups[o["workstream"]])) for o in out]
    return dict(product=product, topic=topic, status=status, workstreams=out)


# ---------- links and competitors ----------

def links_shared(product: str, kind: str | None = None, g=None) -> dict:
    """Links shared in the product's channels with who shared them, where and when. kind: competitor_demo, product_demo, external,
    internal, doc, pr."""
    rs = rows(g, "MATCH (s:Person)-[x:SHARES]->(e:Evidence) WHERE (e)-[:ABOUT]->(:Project {id: $p}) OR e.product = $p "
                 "OPTIONAL MATCH (e)-[:DEMO_OF]->(c:Competitor) RETURN e.id AS id, e.kind AS kind, e.link AS link, e.title AS description, e.external AS external, "
                 "c.name AS competitor, s.id AS by, x.at AS at, x.channel AS channel ORDER BY x.at", {"p": product})
    k = (kind or "").lower()
    if k == "competitor_demo":
        rs = [r for r in rs if r["competitor"]]
    elif k == "product_demo":
        rs = [r for r in rs if "demo" in (r["link"] or "") and not r["external"]]
    elif k in ("external", "internal"):
        rs = [r for r in rs if r["kind"] == "link" and bool(r["external"]) == (k == "external")]
    elif k in ("doc", "pr"):
        rs = [r for r in rs if r["kind"] == k]
    by = defaultdict(lambda: dict(shared_by=[], at=[], channels=set()))
    for r in rs:
        b = by[r["link"]]
        b.update(link=r["link"], description=_clip(r["description"], 90), competitor=r["competitor"])
        if r["by"] not in b["shared_by"]:
            b["shared_by"].append(r["by"])
        b["at"].append((r["at"] or "")[:10])
        b["channels"].add(r["channel"])
    return dict(product=product, kind=kind, links=[{**{k: v for k, v in b.items() if v not in (None, "")}, "channels": sorted(b["channels"]), "at": b["at"][:3]} for b in by.values()])


def competitors(product: str, g=None) -> dict:
    """Competitor products (named by their demo URLs), the demo link and who shared it, and the conversations that discuss each:
    who opened them and who took part, with the opening message."""
    comps = rows(g, "MATCH (c:Competitor)-[:COMPETES_WITH]->(:Project {id: $p}) OPTIONAL MATCH (l:Evidence)-[:DEMO_OF]->(c) "
                    "OPTIONAL MATCH (s:Person)-[:SHARES]->(l) RETURN c.id AS id, c.name AS name, l.link AS demo, collect(DISTINCT s.id) AS demo_shared_by", {"p": product})
    out = []
    for c in comps:
        ms = rows(g, "MATCH (m:Evidence {product: $p})-[:MENTIONS]->(:Competitor {id: $c}) RETURN m.id AS id, m.conv AS conv, m.author AS author, m.kind AS kind, "
                     "m.date AS date, m.excerpt AS text ORDER BY m.date", {"p": product, "c": c["id"]})
        convs = []
        for conv in sorted({m["conv"] for m in ms if m["conv"]}):
            allm = rows(g, "MATCH (m:Evidence {product: $p}) WHERE m.conv = $c RETURN m.id AS id, m.author AS author, m.excerpt AS text ORDER BY m.date, m.id", {"p": product, "c": conv})
            if not allm or "http" in allm[0]["text"] and len(allm) == 1:
                continue
            convs.append(dict(opened_by=allm[0]["author"], first=allm[0]["id"], participants=sorted({m["author"] for m in allm}), opening=_clip(allm[0]["text"], 300)))
        out.append(dict(name=c["name"], demo=c["demo"], demo_shared_by=c["demo_shared_by"], discussions=convs,
                        other_mentions=[dict(id=m["id"], kind=m["kind"]) for m in ms if not m["conv"]][:4]))
    return dict(product=product, competitors=out)


# ---------- rankings ----------

METRICS = {
    "issues_by_company": "company", "issues_by_assignee": "assignee", "issues_resolved_by": "resolved_by", "issues_dismissed_by": "dismissed_by",
    "fix_pr_authors": "fix_author",
}


def rank(product: str, metric: str, status: str | None = None, reopened: bool | None = None, g=None) -> dict:
    """Counts with shared ranks (ties share a rank). metric: issues_by_company, issues_by_assignee, issues_resolved_by,
    issues_dismissed_by, fix_pr_authors (authors of the PRs that fixed issues), prs_by_author. status filters issues as in
    list_issues; reopened=true keeps only issues reopened after the fix or dismissal."""
    if metric == "prs_by_author":
        rs = rows(g, "MATCH (p:Person)-[:AUTHORED]->(e:Evidence {product: $p, kind: 'pr'}) WHERE e.external = false RETURN p.id AS key, count(e) AS n ORDER BY n DESC", {"p": product})
    elif metric in METRICS:
        iss = _issues(g, product, status)
        if reopened:
            iss = [i for i in iss if i["reopened"]]
        field = METRICS[metric]
        if field == "fix_author":
            fx = {r["link"]: r["author"] for r in rows(g, "MATCH (i:Issue {product: $p})-[:FIXED_BY]->(e:Evidence) RETURN e.link AS link, e.author AS author", {"p": product})}
            keys = [fx.get(i["fix_pr"]) for i in iss]
        else:
            keys = [i[field] for i in iss]
        rs = [dict(key=k, n=n) for k, n in Counter(k for k in keys if k).most_common()]
    else:
        return dict(error=f"unknown metric {metric}", metrics=sorted(list(METRICS) + ["prs_by_author"]))
    r_, last = 0, None
    for i, r in enumerate(rs):
        if r["n"] != last:
            r_, last = i + 1, r["n"]
        r["rank"] = r_
    return dict(product=product, metric=metric, status=status, reopened=reopened, top=[r["key"] for r in rs if r["rank"] == 1], ranking=rs[:25])


# ---------- decisions, people, paths ----------

def decision_lineage(product: str, subject: str, as_of: str | None = None, g=None) -> dict:
    """The dated status chain of one issue (by title) or one PR (number or link): each decision with value, window, who decided and the
    quote, newest first, plus claims that were refused (CONFLICTS_WITH). as_of shows the state in force then."""
    s = str(subject).strip()
    target = None
    m = re.search(r"(\d+)\s*$", s)
    if m and ("pull" in s or "pr" in s.lower() or s.isdigit()):
        pr = [p for p in _prs(g, product) if p["number"] == int(m.group(1))]
        target = pr[0]["id"] if pr else None
    if target is None:
        iss = _issues(g, product)
        best = max(iss, key=lambda i: token_set_ratio(i["title"], s), default=None)
        target = best["id"] if best and token_set_ratio(best["title"], s) >= 60 else None
    if target is None:
        return dict(product=product, subject=subject, found=False)
    ds = rows(g, "MATCH (d:Decision)-[:ABOUT]->(x {id: $id}) RETURN d.id AS id, d.topic AS topic, d.value AS value, d.valid_from AS valid_from, d.valid_to AS valid_to, "
                 "d.decided_by AS by, d.quote AS quote, d.source AS source ORDER BY d.topic, d.valid_from DESC", {"id": target})
    cf = rows(g, "MATCH (m:Evidence)-[c:CONFLICTS_WITH]->(d) WHERE d.id = $id OR (d:Decision AND (d)-[:ABOUT]->({id: $id})) RETURN m.id AS msg, c.claimed AS claimed, "
                 "c.by AS by, c.role AS role, c.at AS at, c.quote AS quote, d.value AS against ORDER BY c.at", {"id": target})
    if as_of:
        ds = [d for d in ds if d["valid_from"] <= as_of and (not d["valid_to"] or d["valid_to"] > as_of)]
    return dict(product=product, subject=target, decisions=[{k: v for k, v in d.items() if v} for d in ds], refused_claims=cf)


def who_knows(product: str, topic: str, g=None) -> dict:
    """People who wrote the most about a topic in the product (full-text hits by author), with their role."""
    rs = rows(g, "CALL db.idx.fulltext.queryNodes('Evidence', $q) YIELD node, score WHERE node.product = $p AND node.author STARTS WITH 'eid_' "
                 "RETURN node.author AS id, count(node) AS hits, sum(score) AS weight ORDER BY weight DESC LIMIT 12", {"q": _fts(topic), "p": product})
    ppl = _people(g, [r["id"] for r in rs])
    return dict(product=product, topic=topic, people=[dict(id=r["id"], role=ppl.get(r["id"], {}).get("role"), hits=r["hits"]) for r in rs])


def connection_path(product: str, a: str, b: str, g=None) -> dict:
    """The shortest chain of edges (at most 6) between two nodes by id: people, customers, issues, artifacts, decisions."""
    rs = rows(g, "MATCH (x {id: $a}), (y {id: $b}) CALL algo.SPpaths({sourceNode: x, targetNode: y, relDirection: 'both', maxLen: 6, pathCount: 1}) "
                 "YIELD path RETURN [n IN nodes(path) | n.id] AS ids, [r IN relationships(path) | type(r)] AS rels", {"a": a, "b": b})
    return dict(product=product, a=a, b=b, path=rs[0] if rs else None)


def find_missing(product: str, kind: str, g=None) -> dict:
    """Gaps: unassigned_issues, issues_without_customer, approved_prs_without_action (approved, open, nothing said), docs_without_discussion."""
    if kind == "unassigned_issues":
        r = [i for i in _issues(g, product) if not i["assignee"]]
    elif kind == "issues_without_customer":
        r = [i for i in _issues(g, product) if not i["company"]]
    elif kind == "approved_prs_without_action":
        r = [dict(link=p["link"], title=p["title"]) for p in _prs(g, product) if p["approved"] and p["state"] == "open" and not p["merged"] and not p["action"]]
    elif kind == "docs_without_discussion":
        r = rows(g, "MATCH (d:Evidence {product: $p, kind: 'doc'}) WHERE NOT (:Evidence)-[:LINKS_TO]->(d) RETURN d.id AS id, d.doc_type AS type", {"p": product})
    else:
        return dict(error=f"unknown kind {kind}")
    return dict(product=product, kind=kind, items=r)


# ---------- registry ----------

def _p(**props):
    req = [k for k, v in props.items() if v.pop("required", False)]
    return {"type": "object", "properties": props, "required": req}


S = lambda d, **kw: dict(type="string", description=d, **kw)
PRODUCT = S("the product the question is about", required=True)

TOOLS = {
    "search": (search, "Full-text search over the product's Slack messages, documents, meetings, PRs and links.",
               _p(product=PRODUCT, query=S("words to look for", required=True), kind=S("chat|doc|meeting|meeting_chat|pr|link"), limit=dict(type="integer"))),
    "get_artifact": (get_artifact, "Read one artifact by id (a message comes with its conversation; long texts in parts).",
                     _p(id=S("artifact id from another tool", required=True), product=S("the product"), part=dict(type="integer"))),
    "resolve_entity": (resolve_entity, "Resolve the product (codenames), people by name or role active in the product, customers or companies.",
                       _p(product=PRODUCT, name=S("a person, customer, company or product name"), role=S("a job title, e.g. Engineering Lead"))),
    "doc_discussion": (doc_discussion, "Feedback on one document type (e.g. Market Research Report) from its Slack review and meetings, with reviewer roles and authors.",
                       _p(product=PRODUCT, doc_type=S("document type", required=True), role=S("only feedback from this role"))),
    "list_issues": (list_issues, "Customer-reported issues with status, company, component, assignee, resolver and fix PR, plus counts.",
                    _p(product=PRODUCT, status=S("reported|resolved|dismissed|reopened|unresolved|ever_dismissed"), company=S("company name"),
                       component=S("component name"), person=S("employee id"))),
    "list_prs": (list_prs, "The product's PRs by workstream/topic with outcome (to_merge, to_close, reverted_direction, reverted_bugs, merged, ...).",
                 _p(product=PRODUCT, topic=S("feature or task name"), status=S("to_merge|to_close|reverted|reverted_direction|reverted_bugs|revert|merged|closed|open|approved|not_approved"),
                 author=S("employee id of the PR author"))),
    "links_shared": (links_shared, "Links shared in the product's channels, who shared them, where and when.",
                     _p(product=PRODUCT, kind=S("competitor_demo|product_demo|external|internal|doc|pr"))),
    "competitors": (competitors, "Competitor products: demo links, who shared them, and the conversations discussing each.", _p(product=PRODUCT)),
    "rank": (rank, "Ranked counts with shared ranks for ties (issues by company/assignee/resolver/dismisser, fix PR authors, PRs by author).",
             _p(product=PRODUCT, metric=S("issues_by_company|issues_by_assignee|issues_resolved_by|issues_dismissed_by|fix_pr_authors|prs_by_author", required=True),
                status=S("issue status filter as in list_issues"), reopened=dict(type="boolean"))),
    "decision_lineage": (decision_lineage, "Dated status history of one issue (title) or PR (number), with refused claims.",
                         _p(product=PRODUCT, subject=S("issue title or PR number", required=True), as_of=S("ISO date"))),
    "who_knows": (who_knows, "People who wrote most about a topic in the product.", _p(product=PRODUCT, topic=S("topic", required=True))),
    "connection_path": (connection_path, "Shortest chain of edges between two ids.", _p(product=PRODUCT, a=S("id", required=True), b=S("id", required=True))),
    "find_missing": (find_missing, "Gaps: unassigned_issues, issues_without_customer, approved_prs_without_action, docs_without_discussion.",
                     _p(product=PRODUCT, kind=S("which gap", required=True))),
}
GRAPH_TOOLS = list(TOOLS)
SEARCH_TOOLS = ["search", "get_artifact"]


def schemas(names: list[str]) -> list[dict]:
    return [dict(name=n, description=TOOLS[n][1], parameters=TOOLS[n][2]) for n in names]


def call(name: str, args: dict, allowed: list[str] | None = None, g=None) -> str:
    """Run one tool by name with JSON args; errors come back as JSON for the model to correct."""
    if name not in (allowed or GRAPH_TOOLS):
        return fit(dict(error=f"unknown tool {name}", tools=allowed or GRAPH_TOOLS))
    fn, _, spec = TOOLS[name]
    args = {k: v for k, v in (args or {}).items() if k in spec["properties"]}
    try:
        return fit(fn(g=g, **args))
    except Exception as ex:  # bad arguments or a query error go back to the model as text
        return fit(dict(error=f"{type(ex).__name__}: {str(ex)[:300]}"))
