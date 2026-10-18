"""Study K3 (docs/studies.md): free-form organisational questions about Kubernetes that no single K-template answers.

The gold comes from moot/k1.py's own parsing of the raw git history (kep.yaml status histories, sigs.yaml at every
first-parent commit), never from Moot's graph. Rules, one per kind, as registered:
  7  comparative     of two KEPs of the same SIG, which was in force (implementable or implemented) for more days by a date
  8  multi           which KEPs of a SIG created in a year are no longer in force, and what retired each (the replacing KEP,
                     else its status word)
  9  across teams    who has been a chair or tech lead of both of two SIGs at some point since 2018 (any sigs.yaml commit)
  10 then and now    of a KEP's authors, who led its owning SIG the day it was created, and who leads it on the study date
  11 comparing teams which of two SIGs had more KEPs first reach `implemented` in a year, with both counts (ties skipped)
  12 why             why a KEP is no longer in force: the KEP that replaced it, else its status word, and since when
  13 tenure          who has held a chair or tech-lead seat of a SIG the longest without a break, as of the study date

  python3 -m moot.k3     -> eval/k3/questions.json (questions, gold, dev/test split, sha256); pin the hash, commit, then run arms
"""
from __future__ import annotations

import hashlib
import json
from datetime import date

from . import k1 as K

K.SIGS = ("sig-auth", "sig-node", "sig-network", "sig-storage")
OUT = K.ROOT / "eval" / "k3" / "questions.json"
TODAY = K.TODAY
PER = 15
h = K.h


def days_in_force(k: dict, until: str) -> int:
    """Days with an in-force status, from the status history, up to `until`."""
    total, start = 0, None
    for d, s in k["hist"] + [(until, None)]:
        d = min(d, until)
        if start and (s not in K.IN_FORCE or d == until):
            total += (date.fromisoformat(d) - date.fromisoformat(start)).days
            start = None
        if s in K.IN_FORCE and start is None and d < until:
            start = d
        if d >= until:
            break
    return total


def implemented_on(k: dict) -> str | None:
    return next((d for d, s in k["hist"] if s == "implemented"), None)


def leadership_history() -> dict[str, list[tuple[str, frozenset]]]:
    """sig dir -> [(day, set of chair and tech-lead handles)] at every first-parent sigs.yaml commit where it changed."""
    tip = K.head_rev(K.COM)
    out: dict[str, list] = {}
    for line in K.git(K.COM, "log", "--first-parent", "--reverse", "--format=%H %cs", tip, "--", "sigs.yaml").splitlines():
        sha, day = line.split()
        for s in K.load_yaml(K.show(K.COM, f"{sha}:sigs.yaml")).get("sigs", []):
            lead = frozenset(K.handle(p.get("github")) for role in ("chairs", "tech_leads")
                             for p in (s.get("leadership") or {}).get(role) or [] if isinstance(p, dict) and K.handle(p.get("github")))
            xs = out.setdefault(s.get("dir"), [])
            if not xs or xs[-1][1] != lead:
                xs.append((day, lead))
    return out


def ever(hist: list) -> set:
    return set().union(*[s for _, s in hist]) if hist else set()


def longest(hist: list, until: str) -> tuple[str | None, int]:
    """The handle with the longest unbroken run of seats, and its length in days, up to `until`."""
    best, run_start = {}, {}
    for i, (d, seats) in enumerate(hist + [(until, frozenset())]):
        for p in list(run_start):
            if p not in seats:
                best[p] = max(best.get(p, 0), (date.fromisoformat(d) - date.fromisoformat(run_start.pop(p))).days)
        for p in seats:
            run_start.setdefault(p, d)
    if not best:
        return None, 0
    top = max(best.values())
    who = sorted(p for p, v in best.items() if v == top)
    return (who[0], top) if len(who) == 1 else (None, top)  # a tie has no single answer: the question is skipped


def main() -> None:
    keps = K.keps()
    hist = leadership_history()
    qs = []
    by_sig = {s: sorted(n for n, k in keps.items() if k["sig"] == s) for s in K.SIGS}
    # 7 comparative
    pairs = [(a, b) for s in K.SIGS for a in by_sig[s] for b in by_sig[s] if a < b]
    for a, b in K.pick(pairs, 40, "k3-7"):
        d = K.a_date(f"k3-7{a}{b}", "2021-01-01", "2026-10-01")
        da, db = days_in_force(keps[a], d), days_in_force(keps[b], d)
        if da == db or len([q for q in qs if q["template"] == 7]) >= PER:
            continue
        qs.append(dict(template=7, question=f"Between KEP-{a} ({keps[a]['title']}) and KEP-{b} ({keps[b]['title']}), which one had been in force for longer as of {d}?",
                       gold=dict(kep=f"KEP-{a if da > db else b}"), keps=[f"KEP-{a}", f"KEP-{b}"], date=d))
    # 8 multi-constraint (12 combos with at least one such KEP, 3 with none)
    def gone_in(s, y):
        return sorted([f"KEP-{n}", K.successor(keps[n], keps) or K.status_on(keps[n], TODAY)] for n in by_sig[s]
                      if keps[n]["created"][:4] == str(y) and K.retired_on(keps[n]))
    combos = [(s, y) for s in K.SIGS for y in range(2018, 2026)]
    for s, y in K.pick([c for c in combos if gone_in(*c)], 12, "k3-8") + K.pick([c for c in combos if not gone_in(*c)], 3, "k3-8e"):
        qs.append(dict(template=8, question=f"Which {s} KEPs created in {y} are no longer in force, and what retired each one (the KEP that replaced it, or withdrawn / deferred)?",
                       gold=dict(retired=gone_in(s, y)), sig=s, year=y))
    # 9 people across teams
    sigs_all = sorted(hist)
    spairs = [(a, b) for a in sigs_all for b in sigs_all if a < b and (a in K.SIGS or b in K.SIGS)]
    both = {p: sorted(ever(hist[p[0]]) & ever(hist[p[1]])) for p in spairs}
    pool = K.pick([p for p in spairs if both[p]], 10, "k3-9a") + K.pick([p for p in spairs if not both[p]], 5, "k3-9b")
    for a, b in pool:
        qs.append(dict(template=9, question=f"Has anyone been a chair or tech lead of both {a} and {b} at some point since 2018? Who? Give GitHub handles.",
                       gold=dict(people=both[(a, b)]), sigs=[a, b]))
    # 10 then and now
    now = K.leads_on(TODAY)
    cand = [n for n, k in keps.items() if k["authors"] and k.get("created") and k["sig"] in K.SIGS]
    led = lambda n: set(keps[n]["authors"]) & (set(K.leads_on(keps[n]["created"]).get(keps[n]["sig"], [])) | set(now.get(keps[n]["sig"], [])))
    for n in K.pick([n for n in cand if led(n)], 12, "k3-10") + K.pick([n for n in cand if not led(n)], 3, "k3-10e"):  # 12 with a lead among the authors, 3 without
        k = keps[n]
        then = set(K.leads_on(k["created"]).get(k["sig"], []))
        qs.append(dict(template=10, question=f"Of the authors of KEP-{n} ({k['title']}), who was a chair or tech lead of its owning SIG when it was created, and who is one today ({TODAY})? Give GitHub handles.",
                       gold=dict(then=sorted(a for a in k["authors"] if a in then), now=sorted(a for a in k["authors"] if a in set(now.get(k["sig"], [])))),
                       kep=f"KEP-{n}"))
    # 11 comparing teams
    impl = {s: {} for s in K.SIGS}
    for s in K.SIGS:
        for n in by_sig[s]:
            d = implemented_on(keps[n])
            if d:
                impl[s][d[:4]] = impl[s].get(d[:4], 0) + 1
    tcombos = [(a, b, y) for a in K.SIGS for b in K.SIGS if a < b for y in range(2019, 2026)]
    for a, b, y in K.pick(tcombos, 42, "k3-11"):
        ca, cb = impl[a].get(str(y), 0), impl[b].get(str(y), 0)
        if ca == cb or len([q for q in qs if q["template"] == 11]) >= PER:
            continue
        qs.append(dict(template=11, question=f"Did {a} or {b} have more KEPs reach 'implemented' in {y}? How many each?",
                       gold=dict(sig=a if ca > cb else b, counts={a: ca, b: cb}), sigs=[a, b], year=y))
    # 12 why
    gone = [n for n, k in keps.items() if K.retired_on(k)]
    for n in K.pick(gone, PER, "k3-12"):
        k = keps[n]
        st = K.status_on(k, TODAY)
        qs.append(dict(template=12, question=f"Why is KEP-{n} ({k['title']}) no longer in force, and since when?",
                       gold=dict(retired_by=K.successor(k, keps) or st, since=K.retired_on(k)), kep=f"KEP-{n}"))
    # 13 tenure
    for s in K.pick([x for x in sigs_all if hist[x]], 30, "k3-13"):
        who, d = longest(hist[s], TODAY)
        if not who or len([q for q in qs if q["template"] == 13]) >= PER:
            continue
        qs.append(dict(template=13, question=f"Who has held a chair or tech-lead seat of {s} the longest without a break, as of {TODAY}? Give a GitHub handle.",
                       gold=dict(person=who), sig=s))
    for q in qs:
        q["id"] = "k3-" + h(q["question"])[:10]
    by_t: dict[int, list] = {}
    for q in qs:
        by_t.setdefault(q["template"], []).append(q)
    for t, xs in by_t.items():
        for i, q in enumerate(sorted(xs, key=lambda q: h(q["id"]))):
            q["split"] = "dev" if i < round(len(xs) * 0.3) else "test"
    body = dict(today=TODAY, sigs=list(K.SIGS), questions=sorted(qs, key=lambda q: (q["template"], q["id"])))
    digest = h(json.dumps(body, sort_keys=True))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dict(sha256=digest, **body), indent=1) + "\n")
    print(f"K3: {len(qs)} questions ({', '.join(f't{t}: {len(v)}' for t, v in sorted(by_t.items()))}); "
          f"test {sum(q['split'] == 'test' for q in qs)}; sha256 {digest}")


if __name__ == "__main__":
    main()
