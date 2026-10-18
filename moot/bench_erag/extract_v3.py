"""rules-v3-llm, POST-HOC: written after v1 and v2 were scored. Still blind: question text and document text only.

A local model (ollama, temperature 0, fixed seed) reads one question and its top-10 documents (a question-focused
window of each) and reports, per document: the value it gives for what the question asks, whether it presents that
value as current, superseded or only proposed, any older value it says it replaces, and its date. The model never
decides what to drop. Pairing is rules:

  B supersedes A   the documents give exactly two distinct values for the question, B's is current, and
                   B says it replaces A's value, or A itself marks its value superseded, or both are current and
                   B is dated later
  safety           three or more distinct values: no edge (the documents answer different things); two documents
                   that each supersede the other cancel out; equal values (same numbers, or mostly the same words)
                   are never a conflict; a value longer than MAX_VALUE characters is not a value

Responses are cached by prompt hash in erag-data/v3_cache, so a re-run reproduces the same graph without the model.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request

from moot.bench_erag import DATA, TOP_K
from moot.bench_erag import extract as v1
from moot.bench_erag.corpus import window

EXTRACTOR_VERSION = "rules-v3-llm-posthoc"
MODEL = os.getenv("MOOT_ERAG_V3_MODEL", "qwen2.5:14b-instruct")
ENDPOINT = os.getenv("MOOT_ERAG_OLLAMA", "http://localhost:11434/api/chat")
CACHE = DATA / "v3_cache"
WINDOW = 900
MAX_VALUE = 100   # a value is a number, setting, name or date; a sentence is not a value
PROMPT = """Question: {question}

Below are {n} documents. For EACH document, report what it says about the specific thing the question asks for.
Return JSON: {{"docs": [{{"doc": <number>, "value": <the short specific value this document gives for what the question asks (a number, setting, name, date or choice; at most 12 words), or null if it gives none>, "status": <"current" if presented as the current, applied, approved, updated or final state; "superseded" if the document itself says this value is old, previous, replaced or outdated; "proposed" if only suggested, drafted, requested or under discussion; null if no value>, "replaces": <an older value this document explicitly says was changed or replaced, or null>, "date": <the document's own date as YYYY-MM-DD, or null>}}, ...]}}
Report every document, in order. Do not guess values the document does not state.

{docs}"""


def ask(prompt: str) -> dict:
    key = hashlib.sha256((MODEL + "\n" + prompt).encode()).hexdigest()
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    body = json.dumps(dict(model=MODEL, stream=False, format="json",
                           options=dict(temperature=0, seed=7, num_ctx=6144, num_predict=700),
                           messages=[dict(role="user", content=prompt)])).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        raw = json.loads(r.read())["message"]["content"]
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        out = {"docs": [], "unparsed": raw[:2000]}
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return out


def numbers(v: str) -> list[str]:
    return sorted(re.sub(r"[,\s]", "", x) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", v))


def words(v: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", v.lower()) if w not in v1.STOPWORDS}


def same(a: str, b: str) -> bool:
    if not a or not b:
        return False
    na, nb = numbers(a), numbers(b)
    if na or nb:
        return na == nb
    wa, wb = words(a), words(b)
    return bool(wa and wb) and len(wa & wb) / min(len(wa), len(wb)) >= 0.7


def text(x) -> str:
    return "" if x is None else (json.dumps(x) if not isinstance(x, str) else x).strip()


def edges(question: str, docs: dict[str, str]) -> list[v1.Edge]:
    ids = list(docs)[:TOP_K]
    rendered = "\n\n".join(f"[Document {i}]\n{window(docs[d], question, WINDOW)}" for i, d in enumerate(ids, 1))
    out = ask(PROMPT.format(question=question, n=len(ids), docs=rendered))
    rows = {}
    for r in out.get("docs", []) if isinstance(out, dict) else []:
        try:
            i = int(r.get("doc")) - 1
        except (TypeError, ValueError):
            continue
        val = text(r.get("value"))
        if 0 <= i < len(ids) and val and len(val) <= MAX_VALUE and val.lower() not in ("null", "none", "n/a"):
            rows[ids[i]] = dict(value=val, status=text(r.get("status")).lower(), replaces=text(r.get("replaces")),
                                date=text(r.get("date"))[:10] or v1.written_on(docs[ids[i]]))
    # a changed claim is two values; three or more distinct values mean the documents answer different things
    clusters: list[str] = []
    for r in rows.values():
        if not any(same(r["value"], c) for c in clusters):
            clusters.append(r["value"])
    if len(clusters) != 2:
        return []
    found = {}
    for b, rb in rows.items():
        for a, ra in rows.items():
            if a == b or same(ra["value"], rb["value"]) or rb["status"] != "current":
                continue
            why = None
            if rb["replaces"] and same(rb["replaces"], ra["value"]):
                why = "replaces"
            elif ra["status"] == "superseded":
                why = "status"
            elif ra["status"] == "current" and re.fullmatch(r"\d{4}-\d\d-\d\d", ra["date"] or "") and \
                    re.fullmatch(r"\d{4}-\d\d-\d\d", rb["date"] or "") and rb["date"] > ra["date"]:
                why = "date"
            if why:
                found[(b, a)] = v1.Edge(b, a, ra["value"][:200], rb["value"][:200],
                                        f"{rb['status']} {rb['date']} replaces={rb['replaces']}"[:400],
                                        f"{ra['status']} {ra['date']}"[:400], "llm-" + why)
    return [e for (b, a), e in found.items() if (a, b) not in found]
