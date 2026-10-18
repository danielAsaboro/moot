"""Claim-level citations: every sentence of an answer carries a verbatim quote from a record a tool returned, checked here in
code before anyone sees it.

An answer is a list of claims, each {"text": one sentence or list item, "cite": [{"id": record id, "quote": exact words}]}.
check() lists what is wrong with each claim; the agent gets one chance to repair (no new tool calls); clean() then drops
every claim still unsupported, and an answer left with nothing becomes the fixed abstention line. The model can phrase,
it cannot assert anything the rows do not say.
"""
from __future__ import annotations

import json
import re

ABSTAIN = "Not in Moot's graph: nothing it holds answers this question."
# identifiers a sentence may only name when a cited record names them too
IDENT = re.compile(r"https?://[^\s)\]>,]+|\beid_[0-9a-f]{6,}\b|\bCUST-\d+\b|\bKEP-\d+\b|#\d+\b|\b[A-Z]{1,6}-?\d{2,}\b")
NUM = re.compile(r"(?<![\w.-])\d+(?:\.\d+)?(?![\w-])")
WORD = re.compile(r"[a-z][a-z0-9]+")
STOP = set("""the a an and or of to in on for with by at from as is are was were be been it its this that these those
which who whom what when where why how not no but if then than so such into over under about after before during
also has have had do does did can could would should will may might must their there they them he she his her
our we you your i me my any all each every some more most other""".split())


def norm(s: str) -> str:
    return " ".join(str(s).lower().split())


def words(s: str) -> str:
    """Text as its words, for the word-for-word check: case, spacing and JSON's quotes, brackets and commas don't count, so
    a quote of a field as the tool printed it ("resolved_by": "eid_4b38019b") matches the record that holds it."""
    return " ".join(re.sub(r"[{}\[\],]", " ", re.sub(r"[\"']", "", str(s).lower())).split())


def idents(text: str) -> list[str]:
    """Identifiers a sentence names, without the punctuation that ends the sentence."""
    return [m.rstrip(".,;:") for m in IDENT.findall(text)]


def stems(s: str) -> set[str]:
    """Content words, cut to five letters, so 'resolved' and 'resolution' meet."""
    return {w[:5] for w in WORD.findall(s.lower()) if w not in STOP and len(w) > 2}


def collect(result, into: dict[str, str]) -> None:
    """Every record a tool returned, by id: its string fields joined, so a quote can be checked against them."""
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError:
            return
    if isinstance(result, list):
        for x in result:
            collect(x, into)
    elif isinstance(result, dict):
        # a record's id; records without one are cited by their link, key or name
        rid = next((result[k] for k in ("id", "link", "url", "key", "name", "workstream") if isinstance(result.get(k), str) and result[k]), None)
        if rid:
            text = " \n ".join(str(v) for k, v in result.items() if isinstance(v, (str, int, float)) and v != rid)
            text += " \n " + " \n ".join(str(x) for v in result.values() if isinstance(v, list) for x in v if isinstance(x, (str, int, float)))
            text += " \n " + json.dumps(result, ensure_ascii=False, default=str)  # the record as the tool printed it, fields and all
            into[rid] = (into.get(rid, "") + " \n " + text).strip()
        for v in result.values():
            if isinstance(v, (dict, list)):
                collect(v, into)


def check(claims: list[dict], texts: dict[str, str]) -> list[list[str]]:
    """Problems per claim (an empty list is a supported claim)."""
    out = []
    for c in claims:
        p = []
        text = str(c.get("text", "")).strip()
        cites = [x for x in c.get("cite") or [] if isinstance(x, dict)]
        if not text:
            out.append(["empty claim"])
            continue
        if not cites:
            p.append("no citation")
        support = ""
        for x in cites:
            rid, quote = str(x.get("id", "")), str(x.get("quote", ""))
            if rid not in texts:
                p.append(f"{rid or '(no id)'} was not returned by any tool")
                continue
            if words(quote) not in words(texts[rid]):
                p.append(f"the quote is not word for word in {rid}")
                continue
            if len(quote.split()) < 3 and not IDENT.search(quote) and norm(quote) not in norm(text):
                p.append(f"the quote from {rid} is too short to show anything")
                continue
            support += " \n " + rid + " \n " + quote + " \n " + texts[rid]
        if cites and not p:
            if not stems(text) & stems(support) and not set(idents(text)) & set(idents(support)):
                p.append("the sentence shares no word with what it cites")
            missing = [i for i in idents(text) if norm(i) not in norm(support)]
            if missing:
                p.append("names " + ", ".join(missing[:4]) + " that no cited record contains")
            nums = [n for n in NUM.findall(text) if n not in support]
            if nums:
                p.append("states " + ", ".join(nums[:4]) + " that no cited record contains")
        out.append(p)
    return out


def repair_message(claims: list[dict], problems: list[list[str]]) -> str:
    lines = [f"- claim {i + 1} (\"{c.get('text', '')[:80]}\"): " + "; ".join(p) for i, (c, p) in enumerate(zip(claims, problems)) if p]
    return ("Some claims are not supported by the records the tools returned:\n" + "\n".join(lines) +
            "\nFix them using only those records: quote word for word, or drop the claim. Do not call tools. "
            "Reply with the whole answer again in the same JSON format.")


def clean(claims: list[dict], problems: list[list[str]]) -> list[dict]:
    return [c for c, p in zip(claims, problems) if not p]


def render(claims: list[dict]) -> str:
    """The answer as text, each claim with its citations, for the judge and the reader."""
    if not claims:
        return ABSTAIN
    return "\n".join(f"- {c['text']}" + "".join(f" [{x['id']}]" for x in c.get("cite") or []) for c in claims)
