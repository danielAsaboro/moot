"""Reasons from ADR text: a model reads each ADR's Context, Decision and Consequences and lists the reasons it states,
so a decision whose title names no tool is no longer UNDOCUMENTED by default. A validator decides what is kept.

Two passes, both cached in data/github/<owner>__<repo>/reasons.json so CI, `moot verify` and the hosted site never call a
model (an ADR whose text changed, or that the cache has never seen, is re-read only by `moot ingest-github`):

  extract   one call per ADR. Each reason is a one-sentence restatement plus the exact words that state it. Kept only if
            the quote is a literal span of the ADR (whitespace and markdown emphasis aside), outside its title and
            Status section, at least 20 characters long. The span, section, document and model are stored with it.
            A reason may name a tool it depends on; that tool must be in the catalogue (moot/backtest/tools.py and the
            public-ADR tools) and named in the quote or the ADR's title, or the link is dropped. A linked reason is
            DERIVED_FROM the tool's checked premises (maintained, open source, no known vulnerability), so the GitHub
            and OSV checks reach it two hops down.
  evidence  one call per later ADR, listing the reasons of earlier ADRs that share words with it. A relation is kept only
            if it names a listed reason id and quotes the later ADR exactly; it becomes a SUPPORTS or CONTRADICTS edge from
            that ADR's Evidence node, dated on the day that ADR was decided.

The model never writes Cypher and never touches FalkorDB: it proposes JSON, the validator keeps or drops each item with a
logged reason, and the connector's graph.json is seeded like any other. A reason with no dated evidence stays
`unevidenced`: the verdict rules are unchanged (nothing contradicts it), and the gate answers REVALIDATE, not ALLOW.

Backend: MOOT_REASONS_BACKEND=ollama (default; MOOT_REASONS_MODEL, default qwen3.8:27b at OLLAMA_URL) or groq
(GROQ_API_KEY from the environment or moot/.env; model qwen/qwen3.8-27b). Temperature 0, seed 7.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = os.getenv("MOOT_REASONS_BACKEND", "ollama")
MODELS = {"ollama": os.getenv("MOOT_REASONS_MODEL", "qwen3.8:27b"), "groq": os.getenv("MOOT_REASONS_MODEL", "qwen/qwen3.8-27b")}
OLLAMA = os.getenv("OLLAMA_URL", "http://localhost:11434")
GROQ = "https://api.groq.com/openai/v1/chat/completions"
MAX_REASONS = 4
MIN_QUOTE = 20

EXTRACT_SYSTEM = """You read one architecture decision record (ADR) and list the reasons it gives for its decision: facts about \
the world or the project that, if they stopped being true, would make the decision worth revisiting.
Return only JSON: {"reasons": [{"text": str, "quote": str, "tool": str or null}]}
- text: the reason as one short present-tense sentence ("The team already runs Puppet on every host").
- quote: the exact words of the ADR that state the reason, copied character for character, one sentence or clause.
  Never paraphrase in the quote. Quote the Context, Decision or Consequences, never the title or the Status line.
- tool: if the reason depends on one of the tools listed under "Tools named in this ADR" being healthy (the tool the ADR
  chose, never an alternative it rejected), that tool's name exactly as listed; otherwise null.
Where to look: the Context (or Problem, Background, Decision Drivers) section states the facts and needs the decision answers;
each such statement is a reason ("ADRs are plain text files stored in the project", "the team needs to deploy several times a
day"). The Decision or Consequences sections count only where they say why ("because ...", "so that ...").
At most 4 reasons, the most load-bearing first. Only reasons the ADR states; never infer one. Return {"reasons": []} only when
the ADR gives no reason at all: no Context, or a Context that says nothing beyond restating the decision."""

EVIDENCE_SYSTEM = """You judge whether a later architecture decision record (ADR) affirms or contradicts reasons that earlier \
ADRs in the same repository rest on.
Return only JSON: {"relations": [{"reason_id": str, "rel": "SUPPORTS" or "CONTRADICTS", "quote": str, "why": str}]}
- reason_id: copied exactly from the listing; never invent or renumber one.
- quote: the exact words of the later ADR that affirm or contradict the reason, copied character for character.
- why: one sentence on why the quote affirms or contradicts it.
CONTRADICTS only when the later ADR clearly says the reason is no longer true (the tool was replaced, the constraint went
away, the assumption proved wrong). SUPPORTS only when it clearly says the reason still holds. Mentioning the same topic
is neither. Most ADRs touch none of the listed reasons: then return {"relations": []}."""

STOP = set("""a an the and or of to in on for with by is are be been was were it its this that these those as at from we our
us not no can will would should may might must has have had do does did use used using than then there their they them
which who what when where how all any each more most other some such only also into over under about after before between
adr decision record records status context consequences accepted proposed new one two""".split())


def sha(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:20]


def model_name() -> str:
    return MODELS[BACKEND]


# ---- model calls (only reached on a cache miss)

def _groq_key() -> str | None:
    if os.getenv("GROQ_API_KEY"):
        return os.environ["GROQ_API_KEY"]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("GROQ_API_KEY="):
                return line.split("=", 1)[1].strip() or None
    return None


def call(system: str, user: str) -> str:
    msgs = [dict(role="system", content=system), dict(role="user", content=user)]
    if BACKEND == "groq":
        body = dict(model=model_name(), messages=msgs, temperature=0, seed=7, response_format={"type": "json_object"})
        for attempt in range(6):
            req = urllib.request.Request(GROQ, data=json.dumps(body).encode(), headers={
                "content-type": "application/json", "authorization": f"Bearer {_groq_key()}", "user-agent": "moot"})
            try:
                return json.loads(urllib.request.urlopen(req, timeout=300).read())["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == 5:
                    raise
                time.sleep(float(e.headers.get("retry-after") or 20))
    body = dict(model=model_name(), stream=False, think=False,  # no JSON mode for this MLX build: the reply is parsed
                options=dict(temperature=0, seed=7, num_ctx=16384), messages=msgs)
    for attempt in range(4):
        try:
            req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(body).encode(), headers={"content-type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=1200).read())["message"]["content"]
        except urllib.error.HTTPError as e:  # the MLX build answers a transient 500 under GPU pressure
            if e.code < 500 or attempt == 3:
                raise
            time.sleep(10)
    raise RuntimeError("unreachable")


def available() -> bool:
    if BACKEND == "groq":
        return bool(_groq_key())
    try:
        tags = json.loads(urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=5).read())
        return any(m["name"] == model_name() for m in tags.get("models", []))
    except Exception:
        return False


def parse(reply: str) -> dict:
    m = re.search(r"\{.*\}", reply or "", re.S)
    try:
        x = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        x = {}
    return x if isinstance(x, dict) else {}


# ---- the validator: literal spans only

_DROP = set("`*_")


def _norm(s: str) -> tuple[str, list[int]]:
    """Collapse whitespace, drop markdown emphasis and smart quotes; keep a map from each kept char to its source index."""
    out, idx, space = [], [], False
    for i, ch in enumerate(s):
        if ch in _DROP:
            continue
        ch = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-"}.get(ch, ch)
        if ch.isspace():
            if not space and out:
                out.append(" "); idx.append(i)
            space = True
            continue
        space = False
        out.append(ch); idx.append(i)
    return "".join(out).rstrip(), idx


def find_span(doc: str, quote: str) -> tuple[int, int] | None:
    """[start, end) of `quote` in `doc`, ignoring whitespace runs, markdown emphasis and a trailing full stop."""
    q, _ = _norm(quote.strip().strip('"').strip())
    q = q.rstrip(".")
    if len(q) < MIN_QUOTE:
        return None
    d, idx = _norm(doc)
    at = d.find(q)
    if at < 0:
        return None
    return idx[at], idx[at + len(q) - 1] + 1


HEADING = re.compile(r"^(#{1,6})\s*(.+?)\s*#*\s*$", re.M)


def sections(doc: str) -> list[tuple[int, str]]:
    """(offset, section) for each heading: title, status, context, decision, consequences or other."""
    out = []
    for m in HEADING.finditer(doc):
        h = m.group(2).lower()
        kind = ("title" if len(m.group(1)) == 1 and not out else
                "status" if re.search(r"\bstatus\b", h) else
                "context" if re.search(r"context|problem|background|drivers|why|motivation", h) else
                "decision" if re.search(r"decision|outcome|proposal|solution", h) else
                "consequences" if re.search(r"consequence|implication|pros|cons|result|impact", h) else "other")
        out.append((m.start(), kind))
    return out


def section_at(doc: str, start: int) -> str:
    kind = "preamble"
    for off, k in sections(doc):
        if off <= start:
            kind = k
    return kind


def in_status_line(doc: str, start: int) -> bool:
    line = doc[doc.rfind("\n", 0, start) + 1: doc.find("\n", start) if doc.find("\n", start) >= 0 else len(doc)]
    return bool(re.match(r"\s*[*_]*\s*(status|date|deciders?|technical story)\s*[*_]*\s*:", line, re.I))


def tools_named(text: str, catalogue: dict) -> list[str]:
    return sorted(tid for tid, (_, rx, _) in catalogue.items() if re.search(rx, text, re.I))


def tool_id(name: str | None, catalogue: dict, offered: list[str]) -> str | None:
    if not name:
        return None
    n = str(name).strip().lower()
    for tid in offered:
        if n in (tid, catalogue[tid][0].lower(), catalogue[tid][0].split(" (")[0].lower()):
            return tid
    return None


def validate_reasons(did: str, title: str, doc: str, raw: dict, catalogue: dict, offered: list[str]) -> tuple[list[dict], list[dict]]:
    kept, dropped, seen = [], [], set()
    items = raw.get("reasons") if isinstance(raw.get("reasons"), list) else []
    for r in items:
        if not isinstance(r, dict):
            dropped.append(dict(item=r, why="not an object")); continue
        text, quote = str(r.get("text") or "").strip(), str(r.get("quote") or "")
        span = find_span(doc, quote)
        why = ("no text" if not text else "quote too short" if len(_norm(quote)[0]) < MIN_QUOTE else
               "quote is not a span of the ADR" if not span else
               "quote is in the title or Status" if section_at(doc, span[0]) in ("title", "status") or in_status_line(doc, span[0]) else
               "same span as an earlier reason" if span in seen else
               f"more than {MAX_REASONS} reasons" if len(kept) >= MAX_REASONS else None)
        if why:
            dropped.append(dict(text=text, quote=quote[:200], why=why)); continue
        seen.add(span)
        tid = tool_id(r.get("tool"), catalogue, offered)
        exact = doc[span[0]:span[1]]
        if r.get("tool") and (not tid or not re.search(catalogue[tid][1], exact + "\n" + title, re.I)):
            dropped.append(dict(text=text, tool=r.get("tool"), why="tool link dropped: not a catalogue tool named in the quote or title"))
            tid = None
        kept.append(dict(id=f"r_{did}_{len(kept) + 1}", text=text[:240], quote=exact, span=list(span),
                         section=section_at(doc, span[0]), tool=tid))
    return kept, dropped


def validate_relations(doc: str, raw: dict, listed: set[str]) -> tuple[list[dict], list[dict]]:
    kept, dropped, seen = [], [], set()
    for r in raw.get("relations") if isinstance(raw.get("relations"), list) else []:
        if not isinstance(r, dict):
            dropped.append(dict(item=r, why="not an object")); continue
        rid, rel, quote = str(r.get("reason_id") or ""), str(r.get("rel") or "").upper(), str(r.get("quote") or "")
        span = find_span(doc, quote)
        why = ("reason id not in the listing" if rid not in listed else "rel is not SUPPORTS or CONTRADICTS" if rel not in ("SUPPORTS", "CONTRADICTS")
               else "quote is not a span of the ADR" if not span else "same reason twice" if rid in seen else None)
        if why:
            dropped.append(dict(reason_id=rid, rel=rel, quote=quote[:200], why=why)); continue
        seen.add(rid)
        kept.append(dict(reason_id=rid, rel=rel, quote=doc[span[0]:span[1]], span=list(span), why=str(r.get("why") or "")[:300]))
    return kept, dropped


# ---- prompts

def body_of(doc: str, limit: int = 9000) -> str:
    return doc if len(doc) <= limit else doc[:limit] + "\n[... truncated]"


def extract_prompt(title: str, doc: str, offered: list[str], catalogue: dict) -> str:
    names = ", ".join(catalogue[t][0] for t in offered) or "none"
    return f"Tools named in this ADR: {names}\n\nADR: {title}\n\n{body_of(doc)}"


def words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9-]{2,}", s.lower()) if w not in STOP}


def candidates(doc: str, earlier: list[dict], limit: int = 12) -> list[dict]:
    """Reasons of earlier ADRs sharing at least two content words with this ADR, most overlap first."""
    w = words(doc)
    scored = [(len(words(r["text"] + " " + r["quote"]) & w), r) for r in earlier]
    return [r for n, r in sorted(scored, key=lambda x: (-x[0], x[1]["id"])) if n >= 2][:limit]


def evidence_prompt(title: str, doc: str, listed: list[dict]) -> str:
    lines = "\n".join(f"- {r['id']}: {r['text']} (from {r['decision']}: \"{r['quote'][:160]}\")" for r in listed)
    return f"Reasons earlier ADRs rest on:\n{lines}\n\nLater ADR: {title}\n\n{body_of(doc)}"


# ---- the two passes, cached

def load_cache(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else dict(extract={}, evidence={})


def run(decisions: list[dict], catalogue: dict, cache_path: Path, call_model: bool = True, log=print) -> dict:
    """decisions: [{id, title, decided_on, text}] in force (not proposed or rejected). Returns
    {reasons: {did: [reason]}, relations: {did: [relation]}, stats}. Missing cache entries are filled only if call_model."""
    cache = load_cache(cache_path)
    model = model_name()
    can = call_model and available()
    stats = dict(model=None, extracted=0, not_read=0, reasons=0, dropped=0, tool_links=0, relations=0, relations_dropped=0)
    reasons: dict[str, list[dict]] = {}
    used_models = set()

    def ask(kind: str, did: str, k: str, system: str, user: str) -> dict | None:
        hit = cache[kind].get(did)
        if hit and hit["key"] == k:
            used_models.add(hit["model"])
            return hit
        if not can:
            return None
        t = time.time()
        reply = call(system, user)
        hit = dict(key=k, model=model, backend=BACKEND, reply=reply, seconds=round(time.time() - t, 1))
        cache[kind][did] = hit
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=1, sort_keys=True))
        used_models.add(model)
        log(f"  {kind} {did}: {hit['seconds']}s")
        return hit

    for d in decisions:
        offered = tools_named(d["text"], catalogue)
        user = extract_prompt(d["title"], d["text"], offered, catalogue)
        hit = ask("extract", d["id"], sha(EXTRACT_SYSTEM, user), EXTRACT_SYSTEM, user)
        if not hit:
            stats["not_read"] += 1
            continue
        kept, dropped = validate_reasons(d["id"], d["title"], d["text"], parse(hit["reply"]), catalogue, offered)
        hit_model = hit["model"]
        for r in kept:
            r.update(decision=d["id"], model=hit_model)
        reasons[d["id"]] = kept
        stats["extracted"] += 1
        stats["reasons"] += len(kept)
        stats["dropped"] += len(dropped)
        stats["tool_links"] += sum(1 for r in kept if r["tool"])
        cache["extract"][d["id"]]["dropped"] = dropped

    relations: dict[str, list[dict]] = {}
    ordered = sorted(decisions, key=lambda d: (d["decided_on"], d["id"]))
    for i, d in enumerate(ordered):
        earlier = [r for e in ordered[:i] if e["decided_on"] < d["decided_on"] for r in reasons.get(e["id"], [])]
        listed = candidates(d["text"], earlier)
        if not listed:
            continue
        user = evidence_prompt(d["title"], d["text"], listed)
        hit = ask("evidence", d["id"], sha(EVIDENCE_SYSTEM, user), EVIDENCE_SYSTEM, user)
        if not hit:
            continue
        kept, dropped = validate_relations(d["text"], parse(hit["reply"]), {r["id"] for r in listed})
        for r in kept:
            r.update(model=hit["model"], at=d["decided_on"])
        relations[d["id"]] = kept
        stats["relations"] += len(kept)
        stats["relations_dropped"] += len(dropped)
        cache["evidence"][d["id"]]["dropped"] = dropped
    if cache_path.exists() or cache["extract"]:
        cache_path.write_text(json.dumps(cache, indent=1, sort_keys=True))
    stats["model"] = ", ".join(sorted(used_models)) or None
    return dict(reasons=reasons, relations=relations, stats=stats)
