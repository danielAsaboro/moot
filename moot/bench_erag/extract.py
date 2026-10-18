"""Rule-based supersession extraction over the documents BM25 retrieves for one question. No model, no answer key.

Two steps, both pure functions of document text:

  statements(doc)   sentences where a document retires a value: "changed from X to Y", "X -> Y",
                    "Y (previously X)", "X is outdated", "instead of X", "was X, now Y" ...
  edges(...)        for a statement in document B that retires X, any other retrieved document A that still
                    states X on a line about the same thing (shared topic words, the same identifiers),
                    without mentioning B's new value and without a later date than B, is superseded by B.

The rules were written against a dev sample of corpus documents that appear in none of the 500 questions'
candidate pools, then frozen (EXTRACTOR_VERSION + the file hash go into evidence/run_manifest.json).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

from moot.bench_erag.corpus import STOPWORDS, query_terms

EXTRACTOR_VERSION = "rules-v1"

# ---- values -------------------------------------------------------------------------------------------------
UNIT = (r"(?:ms|msec|s|sec|secs|seconds?|mins?|minutes?|h|hrs?|hours?|d|days?|weeks?|months?|years?|"
        r"[KMGT]i?B|[kKMB]|bps|rps|qps|req/s|tok/s|tokens?|x|GPUs?|nodes?|replicas?|vCPUs?|cores?|users?|seats?)")
VALUE = re.compile(
    r"(?<![\w.$:/-])("
    r"\$\s?\d(?:[\d,]*\d)?(?:\.\d+)?(?:\s?(?:[kKMB]|million|billion))?(?:\s?/\s?[A-Za-z]+)?"   # money
    r"|\d+(?:\.\d+)?\s?%"                                                              # percent
    r"|v?\d+\.\d+(?:\.\d+)+"                                                           # version a.b.c
    r"|20\d\d-\d\d-\d\d"                                                               # iso date
    r"|\d(?:[\d,]*\d)?(?:\.\d+)?\s?" + UNIT + r"(?![A-Za-z])"                                 # number + unit
    r"|\d(?:[\d,]*\d)?(?:\.\d+)?"                                                             # bare number
    r")(?![:/.]?\d)")


def norm(v: str) -> str:
    return re.sub(r"[\s,]", "", v.lower()).replace("seconds", "s").replace("second", "s")


def kind(v: str) -> str:
    v = v.strip()
    if v.startswith("$"):
        return "money"
    if v.endswith("%"):
        return "pct"
    if re.fullmatch(r"20\d\d-\d\d-\d\d", v):
        return "date"
    if re.fullmatch(r"v?\d+\.\d+(?:\.\d+)+", v):
        return "version"
    m = re.fullmatch(r"[\d,.]+\s?(.+)", v)
    return "unit:" + m.group(1).lower().rstrip("s") if m else "num"


def values(text: str) -> list[str]:
    return [m.group(1).strip() for m in VALUE.finditer(text)]


def significant(v: str) -> bool:
    """A bare one-digit number is too common to anchor a supersession on."""
    return kind(v) != "num" or len(re.sub(r"\D", "", v)) >= 2


# ---- supersession statements ---------------------------------------------------------------------------------
V = r"(\$?\s?\d[\w.,%$/ ]{0,18}?)"   # a value-shaped span, refined with VALUE afterwards
CHANGE = (r"(?:chang|updat|mov|rais|lower|increas|decreas|bump|reduc|revis|adjust|switch|cut|extend|shorten|"
          r"correct|tighten|relax|drop|bring|brought|amend|went|go|going|replac|reset|set|shift|migrat|roll|flip)")
PATTERNS = [
    # changed/updated ... from X to Y
    re.compile(CHANGE + r"\w*\b[^.;\n]{0,60}?\bfrom\s+" + V + r"\s+(?:to|->|→)\s+" + V + r"(?=[\s.,;:)]|$)", re.I),
    # X -> Y
    re.compile(V + r"\s*(?:->|→|=>|⇒)\s*" + V + r"(?=[\s.,;:)]|$)"),
    # Y (previously X) / Y (was X) / Y (down from X) / Y (previous ... was X)
    re.compile(V + r"\s*\((?:[^()]{0,40}?\b)?(?:previously|prev\.?|was|were|formerly|down from|up from|old|replacing|"
               r"instead of|vs\.? (?:old|previous)|previous[^()]{0,40}?(?:was|of|:))\s*:?\s*" + V + r"[^()]{0,40}\)", re.I),
    # was X, now Y / from X; now Y
    re.compile(r"\b(?:was|were|used to be|had been)\s+" + V + r"[^.;\n]{0,40}?\b(?:now|currently|is now|are now)\s+(?:is\s+|are\s+)?" + V, re.I),
]
# X marked as old, new value optional: "the old 20% figure", "previous target of 20%", "instead of X", "X is outdated"
OLD_ONLY = [
    re.compile(r"\b(?:previous|previously|prior|old|earlier|original|former|outdated|stale|superseded|deprecated|"
               r"retired)\b[^.;\n]{0,40}?(?:\b(?:was|were)\s|[:=]\s*)" + V, re.I),
    re.compile(r"(?:\b(?:instead of|rather than|no longer)\s+|(?:\(|,\s|—\s?|-\s)not\s+)" + V, re.I),
    re.compile(V + r"[^.;\n]{0,30}?\b(?:is|was|are|were)\s+(?:now\s+)?(?:outdated|obsolete|deprecated|superseded|stale|"
               r"no longer (?:valid|accurate|correct|current|applies)|incorrect|wrong)\b", re.I),
]


# A sentence that reports a measurement moving, or floats a change nobody has made, retires nothing.
OBSERVED = re.compile(r"\b(?:dropp|jump|spik|improv|fell|fall|rose|rise|grew|grow|climb|degrad|regress|surg|plummet|doubl|"
                      r"halv|recover|went|down from|up from|trending|decreas|increasing|show|observ|seeing|saw|peak|tick|"
                      r"monitor|snapshot|metric|telemetry|cpu|memory|queue|lag|count|latency|error rate|hit.?rate|miss|"
                      r"throughput|p\d\d\b)", re.I)
TENTATIVE = re.compile(r"\b(?:propos|maybe|might|idea|consider|revisit|suggest|could|would|if|whether|request|"
                       r"option|scenario|e\.g\.|example|try|tried|trial|test|experiment|ramp|rollout|roll out|canary|"
                       r"plan|draft|tbd|prefer|want|ask|recommend|\?)", re.I)
# ...unless the line says the change is done; a parenthetical about the old value does not make the line tentative
DONE = re.compile(r"\b(?:applied|updated|effective|approved|confirmed|final|finali[sz]ed|agreed|decided|signed|"
                  r"enforced|in effect|now|current(?:ly)?|changed|deployed|rolled|merged|shipped|live)\b", re.I)
PAREN = re.compile(r"\([^()]*\)")
CHAIN = re.compile(r"(?:->|→|=>).{0,25}(?:->|→|=>)")


@dataclass(frozen=True, slots=True)
class Statement:
    doc_id: str
    old: str
    new: str          # "" when the sentence retires a value without naming its replacement
    span: str


def lines(content: str) -> list[str]:
    text = content.replace("\\n", "\n").replace("\\t", " ")
    out: list[str] = []
    for ln in text.split("\n"):
        out.extend(p.strip() for p in re.split(r"(?<=[.!?])\s+(?=[A-Z\[(\"'])", ln) if p.strip())
    return out


def value_at(line: str, start: int) -> str | None:
    """The whole value that begins where a pattern group begins (groups are lazy, so they can stop at "$2" of "$25,000")."""
    m = VALUE.match(line, start) or VALUE.search(line, start, start + 24)
    return m.group(1).strip() if m else None


def statements(doc_id: str, content: str) -> list[Statement]:
    out: dict[tuple, Statement] = {}
    for ln in lines(content):
        if len(ln) > 600:
            ln = ln[:600]
        if OBSERVED.search(ln) or CHAIN.search(ln) or TENTATIVE.search(PAREN.sub(" ", ln)) and not DONE.search(ln):
            continue
        for i, pat in enumerate(PATTERNS):
            for m in pat.finditer(ln):
                a, b = value_at(ln, m.start(1)), value_at(ln, m.start(2))
                if not a or not b:
                    continue
                old, new = (b, a) if i == 2 else (a, b)   # pattern 3 names the new value first
                if norm(old) == norm(new) or kind(old) != kind(new) or not significant(old):
                    continue
                out.setdefault((norm(old), norm(new), ln), Statement(doc_id, old, new, ln))
        for pat in OLD_ONLY:
            for m in pat.finditer(ln):
                old = value_at(ln, m.start(1))
                if not old or not significant(old) or kind(old) == "num" and len(re.sub(r"\D", "", old)) < 3:
                    continue
                others = [v for v in values(ln) if kind(v) == kind(old) and norm(v) != norm(old)]
                out.setdefault((norm(old), norm(others[0]) if others else "", ln),
                               Statement(doc_id, old, others[0] if others else "", ln))
    return list(out.values())


# ---- dates --------------------------------------------------------------------------------------------------
ISO = re.compile(r"\b(20\d\d-\d\d-\d\d)")
HEADER_DATE = re.compile(r"\bDate:\s*([^\n\\]{8,40})")


def written_on(content: str) -> str | None:
    """The first date in the document: headers come first, and later dates are often deadlines, not authorship."""
    found = [(m.start(), m.group(1)) for m in ISO.finditer(content)]
    for m in HEADER_DATE.finditer(content):
        try:
            found.append((m.start(), parsedate_to_datetime(m.group(1).strip()).date().isoformat()))
        except (TypeError, ValueError, IndexError):
            pass
    return min(found)[1] if found else None


# ---- edges ----------------------------------------------------------------------------------------------------
def topic(text: str) -> set[str]:
    return {t for t in query_terms(text) if len(t) > 2 and not t.isdigit() and t not in STOPWORDS and not VALUE.fullmatch(t)}


ANCHOR = re.compile(r"\b[a-z][a-z0-9]*(?:[-_][a-z0-9]+)+\b|\b[a-z]+\d+[a-z0-9]*\b", re.I)


def anchors(text: str) -> set[str]:
    """Identifier-like tokens (dp-132-usw, tier_b, gpu-a100, INF-2345) that pin a line to one specific thing."""
    return {a.lower() for a in ANCHOR.findall(text) if not VALUE.fullmatch(a)}


def has_value(text: str, v: str) -> bool:
    n = norm(v)
    return any(norm(x) == n for x in values(text))


@dataclass(frozen=True, slots=True)
class Edge:
    new_doc: str
    old_doc: str
    old: str
    new: str
    span: str        # the retiring sentence in new_doc
    evidence: str    # the line in old_doc that still states the old value
    rule: str


MIN_SHARED_TOPIC = 3
MIN_QUESTION_TERMS = 2


def edges(question: str, docs: dict[str, str]) -> list[Edge]:
    """Supersession edges among one question's retrieved documents (doc_id -> content)."""
    q = set(query_terms(question))
    split = {d: lines(c) for d, c in docs.items()}
    dated = {d: written_on(c) for d, c in docs.items()}
    found: dict[tuple[str, str], Edge] = {}
    for b, content in docs.items():
        for st in statements(b, content):
            s_topic, s_anchor = topic(st.span), anchors(st.span)
            if len(s_topic & q) < MIN_QUESTION_TERMS:
                continue   # a change, but not about what this question asks
            for a, a_lines in split.items():
                if a == b or (a, b) in found and (b, a) in found:
                    continue
                if st.new and any(has_value(ln, st.new) and len(topic(ln) & s_topic) >= 2 for ln in a_lines):
                    continue   # A already knows the new value
                if dated[a] and dated[b] and dated[a] > dated[b]:
                    continue   # A was written after B
                for ln in a_lines:
                    if not has_value(ln, st.old):
                        continue
                    if any(s.old and norm(s.old) == norm(st.old) for s in statements(a, ln)):
                        continue   # A itself marks the value as old
                    if len(topic(ln) & s_topic) < MIN_SHARED_TOPIC:
                        continue
                    if s_anchor and not (anchors(ln) & s_anchor) and not (anchors("\n".join(a_lines)) & s_anchor):
                        continue
                    found.setdefault((b, a), Edge(b, a, st.old, st.new, st.span[:400], ln[:400],
                                                  "explicit" if st.new else "old-only"))
                    break
    # Two documents that each retire the other's value are a contradiction, not a supersession: keep both.
    return [e for (b, a), e in found.items() if (a, b) not in found]
