"""rules-v2, POST-HOC: written after rules-v1 (extract.py, frozen) was scored at 1/20. Still blind: no answer key.

v1 needed a document to name the value it retires. v2 adds the case where two retrieved documents state the same
claim with different values and neither names the other:

  same claim    a line in A and a line in B share most of their topic words (and their identifiers, and their
                proper nouns), are about what the question asks, and carry values of the same kind that differ
  direction     the line that says it is an update (updated, revised, now, as of, effective, no longer, replaced,
                final, applied ...) wins; failing that, the document written later wins; failing that, no edge
  safety        A is not cut if it also states B's value on a line about the same thing, and two documents that
                each win against the other cancel out

v1's edges are kept; v2 only adds. Everything v1 and v2 each caught is reported separately.
"""
from __future__ import annotations

import re

from moot.bench_erag import extract as v1
from moot.bench_erag.corpus import query_terms

EXTRACTOR_VERSION = "rules-v2-posthoc"

UPDATE = re.compile(r"\b(?:updated?|revised?|revision|now|as of|effective|no longer|replac\w*|supersed\w*|final|finali[sz]ed|"
                    r"applied|correct(?:ed|ion)|latest|current(?:ly)?|changed|new (?:target|value|limit|price|rate|policy)|"
                    r"amended|approved|confirmed|agreed|going forward|from now)\b", re.I)
STALE = re.compile(r"\b(?:previous(?:ly)?|old|earlier|former|outdated|deprecated|draft|proposed|suggest\w*|tentative|"
                   r"initial(?:ly)?|originally)\b", re.I)
PROPER = re.compile(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-zA-Z0-9]+(?:\s[A-Z][a-zA-Z0-9]+)*)")
COMMON = frozenset("The This That These Those For From With And But Not Note Notes Action Status Update Updated Owner Next "
                   "Summary Q1 Q2 Q3 Q4 Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec Monday Tuesday Wednesday Thursday "
                   "Friday Saturday Sunday UTC PT ET Title Date Subject Re Fwd Hi Thanks".split())
MIN_SHARED = 4
MIN_SLOT = 2      # the two values must be values of the same thing
MIN_OVERLAP = 0.5   # shared topic words / topic words of the shorter line


def proper(line: str) -> set[str]:
    return {p.lower() for p in PROPER.findall(line) if p.split()[0] not in COMMON}


UNITS = {"ms": ("s", 1e-3), "msec": ("s", 1e-3), "s": ("s", 1), "sec": ("s", 1), "secs": ("s", 1), "second": ("s", 1),
         "min": ("s", 60), "mins": ("s", 60), "minute": ("s", 60), "h": ("s", 3600), "hr": ("s", 3600), "hrs": ("s", 3600),
         "hour": ("s", 3600), "d": ("s", 86400), "day": ("s", 86400), "week": ("s", 604800), "month": ("mo", 1),
         "year": ("mo", 12), "k": ("", 1e3), "m": ("", 1e6), "b": ("", 1e9), "million": ("", 1e6), "billion": ("", 1e9)}


def amount(v: str) -> tuple[str, float] | None:
    """A value as (unit family, number), so $1,500,000 == $1.5M and 2 days == 48 hours."""
    m = re.fullmatch(r"(\$)?\s?([\d,]*\.?\d+)\s?([a-zA-Z%/]*)", v.strip().replace(" ", ""))
    if not m:
        return None
    n = float(m.group(2).replace(",", ""))
    unit = (m.group(3) or "").lower().split("/")[0].rstrip("s") if m.group(3) not in ("s", "ms") else m.group(3)
    fam, mult = UNITS.get(unit, (unit, 1)) if unit else ("", 1)
    return (("$" if m.group(1) else "") + fam, n * mult)


def same_value(x: str, y: str) -> bool:
    ax, ay = amount(x), amount(y)
    if ax and ay:
        return ax[0] == ay[0] and abs(ax[1] - ay[1]) <= 1e-9 * max(1.0, abs(ax[1]))
    return v1.norm(x) == v1.norm(y)


def slot(line: str, start: int) -> set[str]:
    """The few content words right before a value: what the value is a value of ("retention", "hot", "access")."""
    words = [w for w in re.findall(r"[a-z][a-z_]+", line[max(0, start - 60):start].lower()) if w not in v1.STOPWORDS]
    return set(words[-4:])


def claims(content: str, q: set[str]) -> list[tuple[str, set[str], list[tuple[str, set[str]]]]]:
    """Asserting lines about the question that carry a significant value: (line, topic words, [(value, slot)])."""
    out = []
    for ln in v1.lines(content):
        if len(ln) > 600 or v1.OBSERVED.search(ln) or "?" in ln or re.search(r"->|→|=>", ln):
            continue
        if v1.TENTATIVE.search(v1.PAREN.sub(" ", ln)) and not v1.DONE.search(ln):
            continue
        vals = [(m.group(1).strip(), slot(ln, m.start(1))) for m in v1.VALUE.finditer(ln)
                if v1.significant(m.group(1).strip()) and v1.kind(m.group(1).strip()) != "date"]
        if not vals:
            continue
        t = v1.topic(ln)
        if len(t & q) >= v1.MIN_QUESTION_TERMS:
            out.append((ln, t, vals))
    return out


def same_claim(a: tuple, b: tuple) -> tuple[str, str] | None:
    """(old value in a, new value in b) when the two lines state one claim with different values of the same kind."""
    (la, ta, va), (lb, tb, vb) = a, b
    shared = ta & tb
    if len(shared) < MIN_SHARED or len(shared) / min(len(ta), len(tb)) < MIN_OVERLAP:
        return None
    aa, ab = v1.anchors(la), v1.anchors(lb)
    if (aa or ab) and not aa & ab:
        return None
    pa, pb = proper(la), proper(lb)
    if pa and pb and not pa & pb:
        return None
    for x, sx in va:
        for y, sy in vb:
            if (not any(same_value(x, y2) for y2, _ in vb) and not any(same_value(y, x2) for x2, _ in va)
                    and (amount(x) or ("",))[0] == (amount(y) or ("",))[0] and v1.kind(x)[:4] == v1.kind(y)[:4]
                    and len(sx & sy) >= MIN_SLOT):
                return x, y
    return None


def newer(la: str, lb: str, da: str | None, db: str | None) -> str | None:
    """'a', 'b' or None: which line carries the current value."""
    ua, ub = bool(UPDATE.search(la)) and not STALE.search(la), bool(UPDATE.search(lb)) and not STALE.search(lb)
    if ua != ub:
        return "a" if ua else "b"
    sa, sb = bool(STALE.search(la)), bool(STALE.search(lb))
    if sa != sb:
        return "b" if sa else "a"
    if da and db and da != db:
        return "a" if da > db else "b"
    return None


def entities(question: str) -> set[str]:
    """What the question is about by name: identifiers (dp-132-usw) and proper nouns (Streamly AI)."""
    return v1.anchors(question) | proper(question)


def edges(question: str, docs: dict[str, str]) -> list[v1.Edge]:
    found = {(e.new_doc, e.old_doc): e for e in v1.edges(question, docs)}
    q = set(query_terms(question))
    named = entities(question)
    # a same-claim pair is only about the question's claim if both documents name everything the question names
    cl = {d: claims(c, q) if all(n in c.lower() for n in named) else [] for d, c in docs.items()}
    dated = {d: v1.written_on(c) for d, c in docs.items()}
    ids = list(docs)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            for ca in cl[a]:
                hit = None
                for cb in cl[b]:
                    pair = same_claim(ca, cb)
                    if not pair:
                        continue
                    w = newer(ca[0], cb[0], dated[a], dated[b])
                    if w == "b":
                        hit = (b, a, pair[0], pair[1], cb[0], ca[0])
                    elif w == "a":
                        hit = (a, b, pair[1], pair[0], ca[0], cb[0])
                    if hit:
                        break
                if hit:
                    new_doc, old_doc, old, new, span, evidence = hit
                    # the older document is not stale if it also states the newer value about the same thing
                    if any(any(same_value(x, new) for x, _ in vs) and len(t & v1.topic(span)) >= MIN_SHARED for _, t, vs in cl[old_doc]):
                        break
                    found.setdefault((new_doc, old_doc), v1.Edge(new_doc, old_doc, old, new, span[:400], evidence[:400], "same-claim"))
                    break
    return [e for (n, o), e in found.items() if (o, n) not in found]
