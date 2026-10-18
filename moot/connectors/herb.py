"""Connector: Salesforce's HERB benchmark (enterprise Slack, docs, meetings, PRs) as one company graph.

  moot ingest-herb --product CollaborateForce [--product VizForce] [--heldout]

What it reads (data/herb/raw, revision REVISION, never written to git):
  metadata    employees (Person, role, org), salesforce_team.json (one Team per VP subtree, MEMBER_OF / PART_OF /
              REPORTS_TO), customers (Customer -WORKS_AT-> Company)
  products    Slack messages, documents (base / final / latest), meeting transcripts and chats, URLs, PRs: one Evidence
              node each, id msg: / doc: / mtg: / chat: / pr: / url:<sha1>, dated, ABOUT its Project
The question fields of a product file are dropped on load, before anything else touches the record (KEEP is a whitelist).

Derived layers (no model; HERB's text is templated, so regular expressions read it):
  linker      URLs in a message -> SHARES (Person -> link, doc or PR) and LINKS_TO; @eid_ -> MENTIONS Person; CUST-1234,
              unambiguous company names, product names and codenames -> MENTIONS; meeting "Name: ..." lines -> SPOKE_IN,
              names resolved against that meeting's participants first; a PR titled "Revert PR#N" -> REVERTS
  events      per conversation in bug- and develop- channels: issue_reported / resolved / dismissed / reopened and
              pr_to_merge / to_close / on_hold / reverted, each pinned to one message with a verbatim quote
              (herb_extract.py is the model path for the same closed set; it is written, not run)
  fold        events -> dated status Decisions per Issue and per PR action, each newer one SUPERSEDES the one before
              (valid_from / valid_to). A claim by someone without authority (policy below) is kept as CONFLICTS_WITH
              on the active decision, visible, not applied. PR records give a second chain (open -> reviews ->
              merged / closed) on topic pr:<id>/status.
  competitors a demo URL described "A demo showing how X works" names competitor X (Competitor -[DEMO_OF]-); messages
              naming X MENTIONS it
Seeds one named graph (default `herb`) with moot.graph.seed; idempotent.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit

from ..graph import DATA, graph, seed

REVISION = "a00bca08f9118e482e6de9951fdcb654fbed5343"
RAW = DATA / "herb" / "raw"
BUILD = DATA / "herb" / "build"
GRAPH = "herb"
DEV = ("ExplainabilityForce", "CollaborateForce", "VizForce")
HELDOUT = ("ContentForce", "EdgeForce", "KnowledgeForce", "MonitorForce", "SearchFlow", "SearchForce", "SummarizeForce")
KEEP = ("team", "customers", "slack", "documents", "meeting_transcripts", "meeting_chats", "urls", "prs")
BOT = "slack_admin_bot"
LEADS = {"Engineering Lead", "VP of Engineering", "Product Manager", "Chief Product Officer"}

URL = re.compile(r"https?://[^\s<>|)\]]+")
EID = re.compile(r"eid_[0-9a-f]{8}")
CUST = re.compile(r"CUST-\d{4}")
PR_REF = re.compile(r"\bPR\s?#\s?(\d+)", re.I)
GH_PR = re.compile(r"https://github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)")
REVERT_TITLE = re.compile(r"^\s*Revert\s+(?:PR\s?)?#\s?(\d+)", re.I)
SPEAKER = re.compile(r"^([A-Z][a-z]+(?: [A-Z][a-z]+)+):\s")
DEMO_DESC = re.compile(r"^A demo showing how (.+?) works\.?$")


class HeldOut(ValueError):
    """A held-out product asked for without --heldout."""


def guard(product: str, heldout: bool) -> None:
    if product in HELDOUT and not heldout:
        raise HeldOut(f"{product} is held out for study X1 (docs/studies.md); pass heldout=True only in the frozen scoring run")


def fetch(product: str, heldout: bool = False) -> Path:
    """The product file at REVISION, downloaded once (curl) into data/herb/raw/products."""
    guard(product, heldout)
    path = RAW / "products" / f"{product}.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/datasets/Salesforce/HERB/resolve/{REVISION}/products/{product}.json"
        subprocess.run(["curl", "-sfL", "-o", str(path), url], check=True)
    return path


def load_product(path: Path) -> dict:
    """The product's records with every non-whitelisted field (the questions among them) dropped at once."""
    raw = json.loads(Path(path).read_text())
    kept = {k: raw.get(k) or [] for k in KEEP}
    del raw
    return kept


def load_metadata(raw: Path = RAW) -> dict:
    md = raw / "metadata"
    return dict(employees=json.loads((md / "employee.json").read_text()), teams=json.loads((md / "salesforce_team.json").read_text()),
                customers=json.loads((md / "customers_data.json").read_text()))


# ---------- small text helpers ----------

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9& ]+", " ", (s or "").lower())).strip()


def token_set_ratio(a: str, b: str) -> float:
    """0-100 similarity of two titles ignoring word order and repeats (shared words vs each side's extra words)."""
    ta, tb = set(norm(a).split()), set(norm(b).split())
    if not ta or not tb:
        return 0.0
    common = " ".join(sorted(ta & tb))
    ra, rb = " ".join(sorted(ta - tb)), " ".join(sorted(tb - ta))
    s1, s2 = (common + " " + ra).strip(), (common + " " + rb).strip()
    pairs = [(common, s1), (common, s2), (s1, s2)] if common else [(s1, s2)]
    return 100 * max(SequenceMatcher(None, x, y).ratio() for x, y in pairs)


def words(s: str) -> set[str]:
    stop = {"the", "a", "an", "of", "in", "on", "for", "to", "and", "with", "is", "are", "bug", "issue", "about", "our", "we", "this", "that", "has", "been",
            "incorrect", "due"}
    return {w for w in norm(s).split() if w not in stop and len(w) > 1}


def url_id(link: str) -> str:
    p = urlsplit(link.strip())
    key = f"{p.scheme.lower()}://{p.netloc.lower()}{p.path.rstrip('/')}" + (f"?{p.query}" if p.query else "")
    return "url:" + hashlib.sha1(key.encode()).hexdigest()[:12]


def clean_url(u: str) -> str:
    return u.rstrip(".,;:!?'\"")


def conv_key(herb_id: str) -> str:
    return herb_id.split("-", 1)[0]


def doc_version(doc_id: str) -> tuple[str, str]:
    head, _, rest = doc_id.partition("_")
    return (head, rest) if head in ("final", "latest") and rest else ("base", doc_id)


# ---------- normalize ----------

def artifacts(product: str, rec: dict) -> list[dict]:
    """Every record of one product as a flat dict (Evidence-to-be), in time order. Bot messages are kept apart (system=True)."""
    out = []
    for m in rec["slack"]:
        u = m["Message"]["User"]
        out.append(dict(id=f"msg:{product}/{m['id']}", herb_id=m["id"], kind="chat", date=u["timestamp"], author=u["userId"],
                        channel=m["Channel"]["name"], conv=f"{m['Channel']['name']}/{conv_key(m['id'])}", text=u["text"], title="",
                        system=u["userId"] == BOT))
    for t in rec["meeting_transcripts"]:
        out.append(dict(id=f"mtg:{product}/{t['id']}", herb_id=t["id"], kind="meeting", date=t["date"], author="", channel="",
                        conv="", title=t.get("document_type", ""), text=t["transcript"], participants=list(t.get("participants") or []),
                        doc_type=t.get("document_type", "")))
    for c in rec["meeting_chats"]:
        first = (c.get("text") or "").split("\n", 1)[0].strip()
        date = first if re.match(r"\d{4}-\d\d-\d\dT", first) else ""
        mtg = c["id"][:-5] if c["id"].endswith("_chat") else ""
        out.append(dict(id=f"chat:{product}/{c['id']}", herb_id=c["id"], kind="meeting_chat", date=date, author="", channel="", conv="",
                        title=c["id"], text=c.get("text") or "", meeting=f"mtg:{product}/{mtg}" if mtg else ""))
    for d in rec["documents"]:
        version, base = doc_version(d["id"])
        out.append(dict(id=f"doc:{product}/{d['id']}", herb_id=d["id"], kind="doc", date=d["date"], author=d.get("author", ""), channel="",
                        conv="", title=d.get("type", ""), text=d.get("content", ""), link=d.get("document_link", ""), doc_type=d.get("type", ""),
                        version=version, base=f"doc:{product}/{base}", feedback=d.get("feedback") or ""))
    for p in rec["prs"]:
        owner, repo, number = GH_PR.match(p["link"]).groups()
        reviews = [dict(state=r["state"], login=r["user"]["login"], comment=r.get("comment", ""), at=r.get("submitted_at", "")) for r in p.get("reviews") or []]
        out.append(dict(id=f"pr:{p['id']}", herb_id=p["id"], kind="pr", date=p["created_at"], author=p["user"]["login"], channel="", conv="",
                        title=p["title"].strip(), text=p.get("summary", ""), link=p["link"], repo=f"{owner}/{repo}", number=int(number),
                        external=owner.lower() != "salesforce", state=p["state"], merged=str(p["merged"]) == "True",
                        mergeable=str(p["mergeable"]) == "True", reviews=reviews))
    seen = set()
    for u in rec["urls"]:
        uid = url_id(u["link"])
        if uid in seen:
            continue
        seen.add(uid)
        out.append(dict(id=uid, herb_id=u["id"], kind="link", date="", author="", channel="", conv="", title=u.get("description", ""),
                        text=u.get("description", ""), link=u["link"], external=urlsplit(u["link"]).netloc != "sf-internal.slack.com"))
    split_conversations(out)
    out.sort(key=lambda a: (a["date"] == "", a["date"], a["id"]))
    return out


def split_conversations(arts: list[dict]) -> None:
    """HERB reuses a conversation key (the date part of a message id) for several conversations of one channel; the message
    index restarts at 0 for each. So within (channel, key), in time order, an index 0 opens the next conversation."""
    by = defaultdict(list)
    for a in arts:
        if a["kind"] == "chat":
            by[(a["channel"], conv_key(a["herb_id"]))].append(a)
    for (ch, key), ms in by.items():
        ms.sort(key=lambda a: (a["date"], int(a["herb_id"].split("-")[1]) if a["herb_id"].count("-") >= 2 and a["herb_id"].split("-")[1].isdigit() else 0))
        n = -1
        for a in ms:
            parts = a["herb_id"].split("-")
            if n < 0 or (len(parts) >= 3 and parts[1] == "0"):
                n += 1
            a["conv"] = f"{ch}/{key}/{n}"


def codenames(product: str, arts: list[dict], rec: dict) -> list[str]:
    """Names the product went by: original planning channel names in the bot's first messages and internal PR repos."""
    names = set()
    for a in arts:
        if a["kind"] == "chat" and a["system"]:
            for m in re.finditer(r"beginning of the (?:planning|develop|bug)-(?:[a-z]+-)?([A-Za-z0-9]+?)(?:-PM)? channel", a["text"]):
                names.add(m.group(1))
            for m in re.finditer(r"renamed the channel to planning-([A-Za-z0-9]+?)(?:-PM)?\.", a["text"]):
                names.add(m.group(1))
        if a["kind"] == "chat" and a["channel"].startswith("planning-"):
            names.add(a["channel"].removeprefix("planning-").removesuffix("-PM"))
    for a in arts:
        if a["kind"] == "pr" and not a["external"]:
            names.add(a["repo"].split("/")[1])
    names.discard(product)
    return sorted(n for n in names if len(n) > 2)


# ---------- events (deterministic) ----------

DISMISS = re.compile(r"not a bug|isn't a bug|is not a bug|does(?: not|n't) require (?:a |an )?(?:immediate )?fix|currently expected|no fix (?:is )?(?:needed|required)|doesn't need fixing|"
                     r"expected behavio|by design|as intended|as designed|no changes were necessary|user error|not an issue|no action (?:is )?needed|"
                     r"isn't a bug that requires|not a system issue|a feature, not a bug|known trade-off|limitation of our current", re.I)
RESOLVED = re.compile(r"\b(?:has|have) been (?:resolved|fixed)\b|\bis (?:now )?(?:resolved|fixed)\b", re.I)
REOPENED = re.compile(r"\breopen(?:ed)?\b", re.I)
REPORT_CUE = re.compile(r"\b(?:first up|next|lastly|finally|also|another|we have|there's|there is)\b", re.I)
CLOSE_CUE = re.compile(r"\b(?:unmerged|PR is not merged|not be merged|not merg(?:e|ing)|not to merge|avoid merging|won't merge|will not merge|don't merge|hold off|shouldn't merge|should not merge|close (?:the |this )?PR|"
                       r"close it|not needed|no longer needed|isn't needed|is not needed|not be merged|no need to revert|keep it on hold)\b", re.I)
REVERT_CUE = re.compile(r"\b(?:revert(?:ing|ed)? (?:the |this |it|PR)|proceed with revert|go ahead and revert|should revert|will revert|i'll revert|revert it)\b", re.I)
DIRECTION = re.compile(r"product direction|direction has (?:changed|shifted)|change in (?:product )?direction|new direction|shift in direction|no longer aligns?|strategic shift", re.I)
BUGS = re.compile(r"\bbug|broke|breaking|introduc|regression|errors?\b|failures?\b", re.I)
MERGE_CUE = re.compile(r"\b(?:merge it now|merging (?:it )?now|let's (?:get (?:this|it) )?merge|ready to merge|go ahead and merge|i'll merge|will merge|be merged)\b", re.I)
APPROVE_CUE = re.compile(r"\b(?:approved|approve|lgtm)\b", re.I)
COMPONENT_WORDS = {"Module", "Engine", "Layer", "Component", "System", "Pipeline", "Interface", "Server", "Service", "Framework", "Database", "API",
                   "Control", "Hub", "Tool", "Manager", "Panel", "Gateway", "Store", "Cache", "Scheduler", "Processor", "Processing", "Integration",
                   "Dashboard", "Center", "Suite", "Library", "Platform", "Storage", "Analytics", "Generator", "Logic", "Feature", "Management", "Modules",
                   "Components", "Layers", "Engines", "Systems", "Services"}
COMPONENT = re.compile(r"(?:affects?|affecting|impacting|impacts|in|within|on|at|area is|issues in|causing issues in|problem is with|^|\.\s+|,\s+)\s*(?:the\s+|our\s+|The\s+)?"
                       r"([A-Z][\w\-/]*(?:\s+(?:[A-Z][\w\-/]*|&|and))*)")


def quoted_title(text: str) -> str:
    for m in re.finditer(r"['‘’\"]([A-Z][^'‘’\"\n]{2,100}?)['’\"](?=[\s.,;:!?)]|$)", text):
        t = m.group(1).strip()
        if len(t.split()) >= 2 or t.isupper():
            return t
    return ""


def title_of(text: str) -> str:
    t = quoted_title(text)
    if t:
        return t
    for pat in (r"titled:?\s+([A-Z][^.,;\n]{3,90})", r"\(Title:\s*([^)]+)\)",
                r"(?:problem|issue|bug|concern) with (?:the |a |an )?([A-Za-z][\w\-()&/' ]{3,90}?)(?:[.,;]| in | that | which | where | causing )",
                r"we have (?:a |an )?(?:critical |security |new )?([A-Z][\w\-()&/ ]{3,90}?) (?:issue|vulnerability|bug|problem|flaw)\b",
                r"(?:there's|there is|we have) (?:a |an )([A-Z][\w\-()&/ ]{3,90}?)[.,;]"):
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return ""


def component_of(text: str, title: str) -> str:
    """The affected module: the longest Title Case run after 'affects' / 'in the' / ... that ends in a component word."""
    for m in COMPONENT.finditer(text):
        ws = m.group(1).split()
        while ws and ws[-1] not in COMPONENT_WORDS:
            ws.pop()
        c = " ".join(ws)
        if len(ws) < 2 or (title and norm(c) in norm(title)) or "CUST" in c:
            continue
        return c
    return ""


def about_of(text: str) -> str:
    """The free-text subject of a closing message: 'the bug about incorrect cache invalidation has been resolved'."""
    m = re.search(r"(?:issue|bug|problem) (?:about|regarding|related to|with|concerning) (?:the )?(.+?)(?:,? (?:titled|has been|have been|is now)|[.(]|$)", text, re.I)
    return m.group(1).strip() if m else ""


def is_external_ref(text: str) -> bool:
    return any(o.lower() != "salesforce" for o, _, _ in GH_PR.findall(text))


def units(arts: list[dict]) -> list[list[dict]]:
    """Conversations of bug- and develop- channels: non-bot messages sharing a channel and HERB's conversation key, in time order."""
    by = defaultdict(list)
    for a in arts:
        if a["kind"] == "chat" and not a["system"] and a["channel"].split("-", 1)[0] in ("bug", "develop"):
            by[a["conv"]].append(a)
    out = [sorted(v, key=lambda a: (a["date"], a["id"])) for v in by.values()]
    out.sort(key=lambda u: (u[0]["date"], u[0]["id"]))
    return out


def quote_of(text: str, cue: re.Pattern | None = None, limit: int = 300) -> str:
    """A verbatim sentence of the message: the one holding the cue, else the first."""
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    pick = next((s for s in sents if cue and cue.search(s)), sents[0] if sents else text)
    return pick[:limit]


def ev(type_: str, m: dict, quote: str, **kw) -> dict:
    return dict(type=type_, artifact=m["id"], date=m["date"], speaker=m["author"], channel=m["channel"], quote=quote, **kw)


def own_pr_links(text: str) -> list[str]:
    return [f"https://github.com/{o}/{r}/pull/{n}" for o, r, n in GH_PR.findall(text) if o.lower() == "salesforce"]


def bug_events(u: list[dict]) -> list[dict]:
    out = []
    leader = u[0]["author"]
    unit_text = " ".join(m["text"] for m in u)
    if is_external_ref(unit_text) and not any(own_pr_links(m["text"]) for m in u):
        return out  # open-source references shared for comparison are not our issues
    reopen = next((m for m in u if REOPENED.search(m["text"]) and m["author"] == leader), None) or (
        u[0] if REOPENED.search(u[0]["text"]) else None)
    if reopen:
        title = title_of(reopen["text"]) or about_of(reopen["text"])
        cust = CUST.findall(unit_text)
        out.append(ev("issue_reopened", reopen, quote_of(reopen["text"], REOPENED), issue=title, customer=cust[0] if cust else ""))
        return out
    for i, m in enumerate(u):
        t = m["text"]
        if RESOLVED.search(t) and not DISMISS.search(t):
            title = title_of(t) or about_of(t)
            prs = own_pr_links(t) or [l for x in u[i:] if x["author"] == m["author"] for l in own_pr_links(x["text"])]
            out.append(ev("issue_resolved", m, quote_of(t, RESOLVED), issue=title, about=about_of(t), person=m["author"], pr=prs[0] if prs else ""))
            return out
    dis = next((m for m in u if DISMISS.search(m["text"]) and m["author"] == leader), None)
    if dis and re.search(r"looked into|reviewed|investigat|review(?:ing)?", u[0]["text"] + " " + dis["text"], re.I):
        first = u[0]["text"]
        lead = [m["text"] for m in u[:u.index(dis) + 1] if m["author"] == leader]
        title = next((t for t in map(title_of, lead) if t), "") or about_of(first)
        out.append(ev("issue_dismissed", dis, quote_of(dis["text"], DISMISS), issue=title, about=about_of(first), person=leader,
                      reason=quote_of(dis["text"], DISMISS, 160)))
        return out
    for i, m in enumerate(u):
        t = m["text"]
        if m["author"] != leader or not CUST.search(t) or is_external_ref(t):
            continue
        title = title_of(t)
        if not title:
            continue
        # "Thanks, @eid_a! Next ... @eid_b, can you take this?" -> eid_b; a thank-you alone names nobody
        named = [x for x in EID.findall(re.sub(r"\b(?:[Tt]hanks|[Tt]hank you),? @eid_[0-9a-f]{8}", "", t))]
        assignee = named[-1] if named else ""
        if not assignee:
            nxt = u[i + 1] if i + 1 < len(u) else None
            if nxt and nxt["author"] == leader and EID.search(nxt["text"]) and not CUST.search(nxt["text"]):
                assignee = EID.findall(nxt["text"])[-1]
            else:
                nxt = next((x for x in u[i + 1:] if x["author"] != leader), None)
                assignee = nxt["author"] if nxt else ""
        out.append(ev("issue_reported", m, quote_of(t, re.compile(re.escape(title[:30]))), issue=title, component=component_of(t, title),
                      customer=CUST.findall(t)[0], person=assignee, description=t[:400]))
    return out


def pr_numbers(text: str, own_links: list[str]) -> list[int]:
    return [int(n) for n in PR_REF.findall(text)] + [int(l.rsplit("/", 1)[1]) for l in own_links]


def develop_events(u: list[dict]) -> list[dict]:
    """PR actions said in a develop- conversation, keyed by PR number (the repo is fixed by the fold)."""
    out = []
    unit_text = " ".join(m["text"] for m in u)
    nums = []
    for m in u:
        for n in pr_numbers(m["text"], own_pr_links(m["text"])):
            if n not in nums:
                nums.append(n)
    if not nums or is_external_ref(u[0]["text"]):
        return out
    pr = nums[0]
    direction = bool(DIRECTION.search(unit_text))
    said = [m for m in u if not m["text"].rstrip().endswith("?")]
    closes = [m for m in said if CLOSE_CUE.search(m["text"])]
    reverts = [m for m in said if REVERT_CUE.search(m["text"]) and not CLOSE_CUE.search(m["text"])]
    if direction or closes or reverts:
        # every message that says what to do is a claim; the fold decides which ones carry authority
        reason = "product_direction" if direction else "introduced_bugs" if BUGS.search(unit_text) else "other"
        for m in closes:
            out.append(ev("pr_to_close", m, quote_of(m["text"], CLOSE_CUE), pr=pr, reason=reason))
        for m in reverts:
            out.append(ev("pr_reverted", m, quote_of(m["text"], REVERT_CUE), pr=pr, reason=reason))
        if not out:
            m = next(x for x in u if DIRECTION.search(x["text"]))
            out.append(ev("pr_on_hold", m, quote_of(m["text"], DIRECTION), pr=pr, reason="product_direction"))
        return out
    if own_pr_links(u[0]["text"]):
        approvals = [m for m in u if APPROVE_CUE.search(m["text"]) and m["author"] != u[0]["author"]]
        merge = next((m for m in u if MERGE_CUE.search(m["text"])), None)
        if approvals and merge:
            out.append(ev("pr_to_merge", merge, quote_of(merge["text"], MERGE_CUE), pr=pr))
    return out


def regex_events(arts: list[dict]) -> list[dict]:
    out = []
    for u in units(arts):
        out += bug_events(u) if u[0]["channel"].startswith("bug-") else develop_events(u)
    return out


# ---------- fold ----------

def issue_key(product: str, title: str) -> str:
    return f"iss:{product}:{hashlib.sha1(norm(title).encode()).hexdigest()[:10]}"


def match_issue(issues: dict, e: dict) -> str | None:
    """Which known issue a closing event is about: same normalised title, then token_set_ratio >= 90, then the speaker's
    own open issues in that channel by word overlap with the title or the 'bug about ...' phrase."""
    title = e.get("issue") or ""
    if title:
        for k, i in issues.items():
            if norm(i["title"]) == norm(title):
                return k
        best = max(issues.items(), key=lambda kv: token_set_ratio(kv[1]["title"], title), default=None)
        if best and token_set_ratio(best[1]["title"], title) >= 90:
            return best[0]
    subject = words(" ".join([title, e.get("about") or ""]))
    pool = [(k, i) for k, i in issues.items() if i["channel"] == e["channel"]]
    if e["type"] in ("issue_resolved", "issue_dismissed"):
        mine = [(k, i) for k, i in pool if i["assignee"] == e["speaker"] and i["status"] in ("reported", "reopened")]
        pool = mine or pool
    # a title word counts twice, a description word once; one shared description word alone ("lead") is not enough
    scored = sorted(((2 * len(subject & words(i["title"])) + len(subject & (words(i["description"]) - words(i["title"]))), i["opened"], k)
                     for k, i in pool), reverse=True)
    if scored and scored[0][0] >= 2:
        return scored[0][2]
    return None


def authorised(e: dict, role: str, subject: dict) -> bool:
    """Who may change a status: a lead (LEADS), the issue's assignee or the PR's author; reports and reopenings relay the customer."""
    if e["type"] in ("issue_reported", "issue_reopened"):
        return True
    return role in LEADS or e["speaker"] in (subject.get("assignee"), subject.get("author"))


def fold(product: str, arts: list[dict], events: list[dict], roles: dict) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Events -> (issue rows, decision rows, edge rows, unmatched events). Decisions per topic in time order; same value SUPPORTS, a new value
    from someone authorised SUPERSEDES, from anyone else CONFLICTS_WITH."""
    issues: dict[str, dict] = {}
    decisions, edges = [], []
    active: dict[str, dict] = {}
    unmatched = []

    def decide(topic: str, value: str, e: dict, about: str, subject: dict, **extra):
        cur = active.get(topic)
        if cur and cur["value"] == value:
            edges.append(dict(src=e["artifact"], rel="SUPPORTS", dst=cur["id"], props=dict(at=e["date"], quote=e["quote"], by=e["speaker"])))
            return None  # a restatement changes nothing
        if not authorised(e, roles.get(e["speaker"], ""), subject):
            # a refused claim stays visible: against the decision in force, or against the subject when none is
            edges.append(dict(src=e["artifact"], rel="CONFLICTS_WITH", dst=cur["id"] if cur else about,
                              props=dict(at=e["date"], claimed=value, by=e["speaker"], role=roles.get(e["speaker"], ""), quote=e["quote"], topic=topic)))
            return None
        n = sum(1 for d in decisions if d["topic"] == topic)
        d = dict(id=f"dec:{topic}#{n}", topic=topic, value=value, valid_from=e["date"], valid_to="", decided_by=e["speaker"],
                 quote=e["quote"], source=e["artifact"], title=f"{topic} -> {value}", summary=e["quote"], product=product, **extra)
        if cur:
            cur["valid_to"] = e["date"]
            edges.append(dict(src=d["id"], rel="SUPERSEDES", dst=cur["id"], props=dict(at=e["date"])))
        decisions.append(d)
        active[topic] = d
        edges.append(dict(src=d["id"], rel="ABOUT", dst=about, props={}))
        edges.append(dict(src=d["id"], rel="FROM", dst=e["artifact"], props={}))
        if e["speaker"].startswith("eid_"):
            edges.append(dict(src=e["speaker"], rel="DECIDED", dst=d["id"], props=dict(at=e["date"])))
        return d

    status_of = {"issue_reported": "reported", "issue_resolved": "resolved", "issue_dismissed": "dismissed", "issue_reopened": "reopened"}
    for e in sorted((e for e in events if e["type"].startswith("issue_")), key=lambda e: (e["date"], e["artifact"])):
        if e["type"] == "issue_reported":
            k = match_issue(issues, dict(e, type="lookup")) if e["issue"] else None
            k = k if k and norm(issues[k]["title"]) == norm(e["issue"]) else None
            if k is None:
                k = issue_key(product, e["issue"])
                issues[k] = dict(id=k, product=product, title=e["issue"], description=e.get("description", ""), component=e.get("component", ""),
                                 customer=e.get("customer", ""), assignee=e.get("person", ""), reporter=e["speaker"], opened=e["date"],
                                 channel=e["channel"], status="reported", resolved_by="", dismissed_by="", fix_pr="", reopened=0, source=e["artifact"])
            elif issues[k]["status"] in ("resolved", "dismissed"):
                e = dict(e, type="issue_reopened")  # a settled bug named again is back
            else:
                issues[k]["assignee"] = e.get("person") or issues[k]["assignee"]
        else:
            k = match_issue(issues, e)
            if k is None and e.get("issue") and e["type"] != "issue_reopened":
                # closed in the channel without a report we could read: the closing message is all we know of it
                k = issue_key(product, e["issue"])
                issues[k] = dict(id=k, product=product, title=e["issue"], description="", component=component_of(e["quote"], e["issue"]), customer="",
                                 assignee=e["speaker"], reporter="", opened=e["date"], channel=e["channel"], status="reported", resolved_by="",
                                 dismissed_by="", fix_pr="", reopened=0, source=e["artifact"])
            if k is None:
                unmatched.append(e)
                continue
        i = issues[k]
        value = status_of[e["type"]]
        d = decide(f"{k}/status", value, e, k, i)
        if d is None:
            continue
        i["status"] = value
        if value == "resolved":
            i["resolved_by"] = e.get("person") or e["speaker"]
            i["fix_pr"] = e.get("pr") or i["fix_pr"]
        elif value == "dismissed":
            i["dismissed_by"] = e.get("person") or e["speaker"]
        elif value == "reopened":
            i["reopened"] += 1
            i["reopened_after"] = "dismissed" if i["dismissed_by"] and (not i["resolved_by"]) else "resolved" if i["resolved_by"] else ""
        edges.append(dict(src=e["artifact"], rel="REPORTS_ON", dst=k, props=dict(event=e["type"], at=e["date"])))

    # PR actions: "PR#N" means the internal repo whose PRs are discussed in develop channels most
    prs = {a["id"]: a for a in arts if a["kind"] == "pr" and not a["external"]}
    dev_repo = Counter(a["repo"] for a in prs.values()).most_common(1)
    by_num = {(a["repo"], a["number"]): a for a in prs.values()}
    action_of = {"pr_to_merge": "to_merge", "pr_to_close": "to_close", "pr_on_hold": "on_hold", "pr_reverted": "reverted"}
    for e in sorted((e for e in events if e["type"].startswith("pr_")), key=lambda e: (e["date"], e["artifact"])):
        links = own_pr_links(next((a["text"] for a in arts if a["id"] == e["artifact"]), ""))
        repo = links[0].split("/")[3] + "/" + links[0].split("/")[4] if links else (dev_repo[0][0] if dev_repo else "")
        pr = by_num.get((repo, e["pr"])) or next((a for (r, n), a in by_num.items() if n == e["pr"]), None)
        if pr is None:
            unmatched.append(e)
            continue
        decide(f"{pr['id']}/action", action_of[e["type"]], e, pr["id"], pr, reason=e.get("reason", ""))
    # PR records: open -> each review -> merged / closed
    for pr in prs.values():
        chain = [(pr["date"], "open", pr["author"])] + [(r["at"], {"APPROVED": "approved", "CHANGES_REQUESTED": "changes_requested"}.get(r["state"], ""), r["login"])
                                                       for r in sorted(pr["reviews"], key=lambda r: r["at"])]
        last = max([pr["date"]] + [r["at"] for r in pr["reviews"]])
        if pr["merged"]:
            chain.append((last, "merged", ""))
        elif pr["state"] == "closed":
            chain.append((last, "closed", ""))
        prev = None
        for n, (at, value, who) in enumerate(c for c in chain if c[1]):
            d = dict(id=f"dec:{pr['id']}/status#{n}", topic=f"{pr['id']}/status", value=value, valid_from=at, valid_to="", decided_by=who,
                     quote="", source=pr["id"], title=f"{pr['id']}/status -> {value}", summary=f"PR #{pr['number']} {value}", product=product,
                     dated="last review" if value in ("merged", "closed") else "record")
            if prev:
                prev["valid_to"] = at
                edges.append(dict(src=d["id"], rel="SUPERSEDES", dst=prev["id"], props=dict(at=at)))
            edges.append(dict(src=d["id"], rel="ABOUT", dst=pr["id"], props={}))
            decisions.append(d)
            prev = d
    return list(issues.values()), decisions, edges, unmatched


# ---------- PR workstreams and outcomes ----------

def workstreams(prs: list[dict], fixes: set[str] = frozenset()) -> dict[str, str]:
    """PR id -> workstream id. A PR joins the stream of an earlier PR with (nearly) its title, of the PR it reverts, or of
    the stream its author opened; otherwise it opens a stream owned by its author. A bug fix (a PR linked from a bug-
    channel) is a stream of its own."""
    ws, owner_of, titles = {}, {}, []
    for p in sorted(prs, key=lambda p: (p["repo"], p["number"])):
        if p["id"] in fixes:
            ws[p["id"]] = f"fix:{p['repo']}#{p['number']}"
            continue
        m = REVERT_TITLE.match(p["title"])
        target = next((q for q in prs if m and q["repo"] == p["repo"] and q["number"] == int(m.group(1))), None)
        if target and target["id"] in ws:
            ws[p["id"]] = ws[target["id"]]
            continue
        same = next((w for t, w in titles if token_set_ratio(t, p["title"]) >= 90), None)
        if same:
            ws[p["id"]] = same
        elif p["author"] in owner_of:
            ws[p["id"]] = owner_of[p["author"]]
        else:
            ws[p["id"]] = owner_of[p["author"]] = f"ws:{p['repo']}#{p['number']}"
        titles.append((p["title"], ws[p["id"]]))
    return ws


def pr_outcomes(prs: list[dict], decisions: list[dict]) -> dict[str, dict]:
    """Per internal PR: approved, reverted (and why, from the revert PR's own summary), the team's last action, and the
    outcome a reader asks for: reverted_direction | reverted_bugs | revert | to_close | to_merge | merged | closed | open."""
    out = {p["id"]: dict(approved=any(r["state"] == "APPROVED" for r in p["reviews"]), reverted_by="", revert_reason="", reverts="", action="") for p in prs}
    by_num = {(p["repo"], p["number"]): p for p in prs}
    for p in prs:
        m = REVERT_TITLE.match(p["title"])
        if m and (p["repo"], int(m.group(1))) in by_num:
            t = by_num[(p["repo"], int(m.group(1)))]
            s = p["text"] + " " + p["title"]
            reason = "product_direction" if DIRECTION.search(s) else "introduced_bugs" if BUGS.search(s) else "other"
            out[t["id"]].update(reverted_by=p["id"], revert_reason=reason)
            out[p["id"]]["reverts"] = t["id"]
    for d in decisions:
        if d["topic"].endswith("/action") and not d["valid_to"]:
            out[d["topic"].rsplit("/", 1)[0]]["action"] = d["value"]
    for p in prs:
        o = out[p["id"]]
        if o["reverts"]:
            o["outcome"] = "revert"
        elif o["reverted_by"]:
            o["outcome"] = "reverted_direction" if o["revert_reason"] == "product_direction" else "reverted_bugs" if o["revert_reason"] == "introduced_bugs" else "reverted"
        elif p["merged"]:
            o["outcome"] = "merged"
        elif o["action"] == "to_close" and o["approved"]:
            o["outcome"] = "to_close"
        elif o["approved"] and p["state"] == "open":
            o["outcome"] = "to_merge"
        else:
            o["outcome"] = p["state"]
    return out


# ---------- build ----------

def org_rows(md: dict) -> tuple[list[dict], list[dict]]:
    nodes, edges = [], []
    for e in md["employees"].values():
        nodes.append(dict(label="Person", id=e["employee_id"], props=dict(name=e["name"], role=e["role"], location=e.get("location", ""), org=e.get("org", ""))))

    def walk(node: dict, team: str, boss: str | None):
        eid = node.get("employee_id")
        if eid:
            edges.append(dict(src=eid, rel="MEMBER_OF", dst=team, props={}))
            if boss:
                edges.append(dict(src=eid, rel="REPORTS_TO", dst=boss, props={}))
        for k, v in node.items():
            if isinstance(v, list):
                for child in v:
                    if isinstance(child, dict):
                        walk(child, team, eid or boss)

    for vp in md["teams"]:
        team = f"team:{vp['employee_id']}"
        nodes.append(dict(label="Team", id=team, props=dict(name=f"{vp['name']}'s organisation", lead=vp["employee_id"])))
        walk(vp, team, None)
    companies = sorted({c["company"] for c in md["customers"]})
    for c in companies:
        nodes.append(dict(label="Company", id=f"co:{c}", props=dict(name=c)))
    for c in md["customers"]:
        nodes.append(dict(label="Customer", id=c["id"], props=dict(name=c["name"], role=c.get("role", ""), company=c["company"])))
        edges.append(dict(src=c["id"], rel="WORKS_AT", dst=f"co:{c['company']}", props={}))
    return nodes, edges


def product_rows(product: str, rec: dict, md: dict, events: list[dict] | None = None) -> tuple[list[dict], list[dict], dict]:
    arts = artifacts(product, rec)
    roles = {k: v["role"] for k, v in md["employees"].items()}
    names = defaultdict(list)
    for k, v in md["employees"].items():
        names[v["name"]].append(k)
    cust = {c["id"]: c for c in md["customers"]}
    companies = {c["company"] for c in md["customers"]}
    aliases = codenames(product, arts, rec)
    nodes = [dict(label="Project", id=product, props=dict(name=product, aliases=aliases))]
    edges = []
    for eid in rec["team"]:
        edges.append(dict(src=eid, rel="MEMBER_OF", dst=product, props={}))
    for cid in rec["customers"]:
        edges.append(dict(src=cid, rel="CUSTOMER_OF", dst=product, props={}))
    known = {a["id"] for a in arts}
    docs = [a for a in arts if a["kind"] == "doc"]
    prs = [a for a in arts if a["kind"] == "pr"]
    pr_by_link = {a["link"]: a for a in prs}
    link_by_url = {a["link"]: a for a in arts if a["kind"] == "link"}
    competitors = {}
    for a in arts:
        if a["kind"] == "link" and (m := DEMO_DESC.match(a["text"].strip())) and not a["link"].startswith("https://sf-internal"):
            competitors[m.group(1)] = a["id"]
    named = r"([A-Z][\w\-]*(?: [A-Z][\w\-]*){0,3})"
    for a in arts:  # a competitor also named in so many words: "a competitor product called X", "reading about X, a competitor"
        if a["kind"] == "chat" and not a["system"]:
            for m in re.finditer(r"competitor(?: product)? called " + named + r"|reading about " + named + r",? (?:a|one of our|which is a)(?: \w+)? competitor", a["text"]):
                nm = m.group(1) or m.group(2)
                if nm and nm not in competitors and nm != product and nm not in aliases:
                    competitors[nm] = ""
    for name, lid in competitors.items():
        cid = f"comp:{product}/{norm(name).replace(' ', '-')}"
        nodes.append(dict(label="Competitor", id=cid, props=dict(name=name, product=product)))
        if lid:
            edges.append(dict(src=lid, rel="DEMO_OF", dst=cid, props={}))
        edges.append(dict(src=cid, rel="COMPETES_WITH", dst=product, props={}))
    comp_re = {name: re.compile(r"\b" + re.escape(name) + r"\b", re.I) for name in competitors}
    alias_re = re.compile(r"\b(" + "|".join(re.escape(x) for x in [product, *aliases]) + r")\b")
    company_re = re.compile(r"\b(" + "|".join(re.escape(c) for c in sorted(companies, key=len, reverse=True)) + r")\b")
    extra_links = {}

    def doc_for(url: str):
        hits = [d for d in docs if d["link"] and (url.startswith(d["link"]) or d["link"].startswith(url))]
        return max(hits, key=lambda d: len(d["link"])) if hits else None

    fixes = {pr_by_link[l]["id"] for a in arts if a["kind"] == "chat" and a["channel"].startswith("bug-") for l in own_pr_links(a["text"]) if l in pr_by_link}
    ws = workstreams([p for p in prs if not p["external"]], fixes)
    team = set(rec["team"])
    active = Counter(a["author"] for a in arts if a["author"].startswith("eid_"))
    for a in arts:
        if a["kind"] == "chat" and a["system"]:
            continue
        props = {k: v for k, v in a.items() if k not in ("id", "reviews", "participants", "system") and not isinstance(v, (list, dict))}
        props.update(product=product, excerpt=a["text"], text="")  # full text lives in `excerpt` (the full-text index field)
        props.pop("text")
        if a["kind"] == "meeting":
            props["participants"] = a["participants"]
        if a["kind"] == "pr":
            props["workstream"] = ws.get(a["id"], "")
            props["review_states"] = [r["state"] for r in a["reviews"]]
        nodes.append(dict(label="Evidence", id=a["id"], props=props))
        edges.append(dict(src=a["id"], rel="ABOUT", dst=product, props={}))
        if a["author"].startswith("eid_"):
            edges.append(dict(src=a["author"], rel="AUTHORED", dst=a["id"], props=dict(at=a["date"])))
        for r in a.get("reviews", []):
            if r["login"].startswith("eid_"):
                edges.append(dict(src=r["login"], rel="REVIEWED", dst=a["id"], props=dict(state=r["state"], at=r["at"], comment=r["comment"][:600])))
        if a["kind"] == "meeting":
            for p in a["participants"]:
                edges.append(dict(src=p, rel="ATTENDED", dst=a["id"], props=dict(at=a["date"])))
            spoke = Counter()
            for line in a["text"].splitlines():
                if (m := SPEAKER.match(line)):
                    nm = m.group(1)
                    same = [p for p in names.get(nm, [])]
                    # a speaker is one of the meeting's participants, else a namesake on the product's team, else an author in it
                    cands = [p for p in a["participants"] if p in same] or [p for p in same if p in team] or [p for p in same if p in active] or same
                    if cands:
                        spoke[sorted(cands, key=lambda p: -active.get(p, 0))[0]] += 1
            for p, c in spoke.items():
                edges.append(dict(src=p, rel="SPOKE_IN", dst=a["id"], props=dict(lines=c, at=a["date"])))
        if a["kind"] == "pr" and (m := REVERT_TITLE.match(a["title"])):
            tgt = next((p for p in prs if p["repo"] == a["repo"] and p["number"] == int(m.group(1))), None)
            if tgt:
                edges.append(dict(src=a["id"], rel="REVERTS", dst=tgt["id"], props=dict(at=a["date"])))
        if a["kind"] not in ("chat", "meeting_chat", "meeting"):
            continue
        text = a["text"]
        for eid in sorted(set(EID.findall(text))):
            edges.append(dict(src=a["id"], rel="MENTIONS", dst=eid, props=dict(at=a["date"])))
        for cid in sorted(set(CUST.findall(text))):
            if cid in cust:
                edges.append(dict(src=a["id"], rel="MENTIONS", dst=cid, props=dict(at=a["date"])))
        for co in sorted(set(company_re.findall(text))):
            edges.append(dict(src=a["id"], rel="MENTIONS", dst=f"co:{co}", props=dict(at=a["date"])))
        if alias_re.search(text):
            edges.append(dict(src=a["id"], rel="MENTIONS", dst=product, props=dict(at=a["date"])))
        for name, rx in comp_re.items():
            if rx.search(text):
                edges.append(dict(src=a["id"], rel="MENTIONS", dst=f"comp:{product}/{norm(name).replace(' ', '-')}", props=dict(at=a["date"])))
        for url in sorted({clean_url(u) for u in URL.findall(text)}):
            tgt = pr_by_link.get(url) or doc_for(url) or link_by_url.get(url)
            if tgt is None:
                uid = url_id(url)
                if uid not in known and uid not in extra_links:
                    extra_links[uid] = dict(label="Evidence", id=uid, props=dict(kind="link", link=url, title="", excerpt="", product=product, date="",
                                                                                 external=urlsplit(url).netloc != "sf-internal.slack.com", herb_id=""))
                tid = uid
            else:
                tid = tgt["id"]
            edges.append(dict(src=a["id"], rel="LINKS_TO", dst=tid, props=dict(at=a["date"])))
            if a["author"].startswith("eid_"):
                edges.append(dict(src=a["author"], rel="SHARES", dst=tid, props=dict(at=a["date"], via=a["id"], channel=a["channel"])))
    nodes += list(extra_links.values())
    for a in arts:
        if a["kind"] == "doc" and a["version"] != "base" and a["base"] in known:
            edges.append(dict(src=a["id"], rel="VERSION_OF", dst=a["base"], props=dict(version=a["version"])))
        if a["kind"] == "meeting_chat" and a.get("meeting") in known:
            edges.append(dict(src=a["id"], rel="CHAT_OF", dst=a["meeting"], props={}))

    events = regex_events(arts) if events is None else events
    issues, decisions, dedges, unmatched = fold(product, arts, events, roles)
    for i in issues:
        nodes.append(dict(label="Issue", id=i["id"], props={k: v for k, v in i.items() if k != "id"}))
        edges.append(dict(src=i["id"], rel="ABOUT", dst=product, props={}))
        if i["customer"] in cust:
            edges.append(dict(src=i["id"], rel="REPORTED_BY", dst=i["customer"], props=dict(at=i["opened"])))
        if i["assignee"].startswith("eid_"):
            edges.append(dict(src=i["id"], rel="ASSIGNED_TO", dst=i["assignee"], props=dict(at=i["opened"])))
        if i["resolved_by"].startswith("eid_"):
            edges.append(dict(src=i["resolved_by"], rel="RESOLVED", dst=i["id"], props={}))
        if i["dismissed_by"].startswith("eid_"):
            edges.append(dict(src=i["dismissed_by"], rel="DISMISSED", dst=i["id"], props={}))
        if i["fix_pr"] in pr_by_link:
            edges.append(dict(src=i["id"], rel="FIXED_BY", dst=pr_by_link[i["fix_pr"]]["id"], props={}))
    for d in decisions:
        nodes.append(dict(label="Decision", id=d["id"], props={k: v for k, v in d.items() if k != "id"}))
    edges += dedges
    outcomes = pr_outcomes([p for p in prs if not p["external"]], decisions)
    for n in nodes:
        if n["label"] == "Evidence" and n["id"] in outcomes:
            n["props"].update(outcomes[n["id"]])
    report = dict(product=product, aliases=aliases, artifacts=Counter(a["kind"] for a in arts), events=Counter(e["type"] for e in events),
                  issues=Counter(i["status"] for i in issues), unmatched=len(unmatched), conflicts=sum(e["rel"] == "CONFLICTS_WITH" for e in dedges),
                  competitors=sorted(competitors))
    return nodes, edges, report


INDEXES = [("Evidence", "id"), ("Person", "id"), ("Team", "id"), ("Project", "id"), ("Customer", "id"), ("Company", "id"), ("Issue", "id"),
           ("Decision", "id"), ("Competitor", "id"), ("Evidence", "product"), ("Issue", "product"), ("Evidence", "kind")]


def ingest(products: list[str], graph_name: str = GRAPH, heldout: bool = False, fresh: bool = True, raw: Path = RAW,
           events_by_product: dict | None = None) -> dict:
    """Build one graph of these products (plus HERB's metadata) and seed it. fresh=True drops the graph first."""
    for p in products:
        guard(p, heldout)
    md = load_metadata(raw)
    nodes, edges = org_rows(md)
    reports = []
    for p in products:
        path = raw / "products" / f"{p}.json"
        if not path.exists():
            path = fetch(p, heldout)
        n, e, r = product_rows(p, load_product(path), md, (events_by_product or {}).get(p))
        nodes += n
        edges += e
        reports.append(r)
    seen, uniq = set(), []
    for n in nodes:
        if (n["label"], n["id"]) not in seen:
            seen.add((n["label"], n["id"]))
            uniq.append(n)
    ids = {n["id"] for n in uniq}
    edges = [e for e in edges if e["src"] in ids and e["dst"] in ids]
    BUILD.mkdir(parents=True, exist_ok=True)
    out = BUILD / f"{graph_name}.json"
    out.write_text(json.dumps(dict(nodes=uniq, edges=edges)))
    g = graph(graph_name)
    stats = seed(g, out, fresh=fresh)
    for label, prop in INDEXES:
        try:
            g.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
        except Exception as ex:
            if "already indexed" not in str(ex).lower():
                raise
    for label, props in (("Issue", ("title", "description")), ("Competitor", ("name",))):
        try:
            g.query(f"CALL db.idx.fulltext.createNodeIndex('{label}', {', '.join(repr(p) for p in props)})")
        except Exception as ex:
            if "already indexed" not in str(ex).lower():
                raise
    return dict(graph=graph_name, stats=stats, products=reports)
