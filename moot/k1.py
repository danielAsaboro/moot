"""Study K1 (docs/studies.md): questions about Kubernetes as an organisation, and their gold, from raw git history.

The gold is computed here with its own parsing of the two checkouts, not through Moot's graph or its connectors:
  kubernetes/enhancements   every kep.yaml's status over time (git log of the file), replaces / superseded-by, authors
  kubernetes/community      sigs.yaml at the last commit before a date: each SIG's chairs and tech leads

  python3 -m moot.k1        -> eval/k1/questions.json (questions, gold, dev/test split, sha256); pin the hash, commit, then run arms
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ENH = ROOT / "data" / "github" / ".repos" / "kubernetes__enhancements"
COM = ROOT / "data" / "github" / ".repos" / "kubernetes__community"
import sys

STUDY = sys.argv[sys.argv.index("--study") + 1] if "--study" in sys.argv else "k1"  # k3's questions come from moot/k3.py
OUT = ROOT / "eval" / STUDY / "questions.json"
SIGS = ("sig-auth", "sig-node", "sig-network", "sig-storage") if STUDY != "k1" else ("sig-auth", "sig-node")
PER_TEMPLATE = 15
TODAY = "2026-10-17"
IN_FORCE = {"implementable", "implemented"}


def git(d: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True, errors="replace").stdout


def show(d: Path, spec: str) -> str:
    return subprocess.run(["git", "-C", str(d), "cat-file", "-p", spec], capture_output=True, text=True, errors="replace").stdout


def h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def handle(a) -> str:
    return str(a).strip().lstrip("@").split()[0].lower() if a else ""


def load_yaml(text: str) -> dict:
    """sigs.yaml at some commits has a stray tab; YAML forbids tabs in indentation, so read it with tabs as spaces."""
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError:
        try:
            return yaml.safe_load(text.replace("\t", "  ")) or {}
        except yaml.YAMLError:
            return {}


def head_rev(d: Path) -> str:
    for ref in ("refs/heads/master", "refs/heads/main", "refs/remotes/origin/HEAD"):
        r = git(d, "rev-parse", "--verify", "-q", ref).strip()
        if r:
            return r
    return git(d, "rev-list", "-1", "--all").strip()


def keps() -> dict[str, dict]:
    rev = head_rev(ENH)
    out = {}
    for f in git(ENH, "ls-tree", "-r", "--name-only", rev).splitlines():
        if not f.endswith("/kep.yaml") or f.split("/")[1] not in SIGS:
            continue
        try:
            y = yaml.safe_load(show(ENH, f"{rev}:{f}")) or {}
        except yaml.YAMLError:
            continue
        num = str(y.get("kep-number", "")).strip().strip('"')
        if not num.isdigit():
            continue
        hist = []
        for line in git(ENH, "log", "--reverse", "--format=%H %cs", rev, "--", f).splitlines():
            sha, day = line.split()
            try:
                st = str((yaml.safe_load(show(ENH, f"{sha}:{f}")) or {}).get("status", "")).lower()
            except yaml.YAMLError:
                st = ""
            hist.append((day, st))
        out[num] = dict(num=num, path=f, sig=y.get("owning-sig"), created=str(y.get("creation-date", "")).strip("'\"")[:10], status=str(y.get("status", "")).lower(), title=str(y.get("title", "")),
                        authors=[handle(a) for a in y.get("authors") or [] if handle(a)], hist=hist,
                        replaces=[re.sub(r"\D", "", str(x)) for x in y.get("replaces") or []],
                        superseded_by=[re.sub(r"\D", "", str(x)) for x in y.get("superseded-by") or []])
    return out


_leads_cache: dict[str, dict] = {}


def leads_on(day: str) -> dict[str, list[str]]:
    """sig dir -> sorted chair and tech-lead handles in sigs.yaml at the last commit on or before `day`."""
    if day not in _leads_cache:
        rev = git(COM, "rev-list", "-1", f"--before={day}T23:59:59", head_rev(COM)).strip()
        y = load_yaml(show(COM, f"{rev}:sigs.yaml")) if rev else {}
        _leads_cache[day] = {s["dir"]: sorted({handle(p.get("github")) for role in ("chairs", "tech_leads")
                                                for p in (s.get("leadership") or {}).get(role) or [] if handle(p.get("github"))})
                             for s in y.get("sigs", [])}
    return _leads_cache[day]


def status_on(k: dict, day: str) -> str | None:
    st = None
    for d, s in k["hist"]:
        if d <= day:
            st = s
    return st


def successor(k: dict, all_keps: dict) -> str | None:
    cands = [x for x in k["superseded_by"] if x in all_keps] + [n for n, o in all_keps.items() if k["num"] in o["replaces"] and n != k["num"]]
    return f"KEP-{sorted(set(cands))[0]}" if cands else None


def retired_on(k: dict) -> str | None:
    """The first commit that set a status out of force (withdrawn, replaced, deferred), after it had been in force."""
    was = False
    for d, s in k["hist"]:
        if s in IN_FORCE:
            was = True
        elif s in ("withdrawn", "replaced", "deferred") and (was or k["hist"][0][1] not in IN_FORCE):
            return d
    return None


def pick(pool: list, n: int, salt: str) -> list:
    return sorted(pool, key=lambda x: h(salt + str(x)))[:n]


def a_date(seed: str, lo: str = "2019-01-01", hi: str = "2026-10-01") -> str:
    a, b = date.fromisoformat(lo), date.fromisoformat(hi)
    return (a + timedelta(days=int(h(seed), 16) % (b - a).days)).isoformat()


def main() -> None:
    if STUDY not in ("k1", "k2"):
        raise SystemExit(f"moot.k1 writes K1 and K2 only; {STUDY}'s questions come from its own module")
    K = keps()
    qs = []
    # (1) which KEP replaced KEP-X, and when (the commit that took X out of force)
    pool = [n for n, k in K.items() if successor(k, K) and retired_on(k)]
    for n in pick(pool, PER_TEMPLATE, "t1"):
        k = K[n]
        qs.append(dict(template=1, question=f"Which KEP replaced KEP-{n} ({k['title']}), and on what date did KEP-{n} stop being in force?",
                       gold=dict(kep=successor(k, K), date=retired_on(k)), kep=f"KEP-{n}"))
    # (2) who led the SIG that answers for KEP-X on date D
    pool = [n for n, k in K.items() if k["sig"] in SIGS]
    for n in pick(pool, PER_TEMPLATE, "t2"):
        k = K[n]
        d = a_date("t2" + n)
        qs.append(dict(template=2, question=f"Who were the chairs and tech leads of the SIG that owns KEP-{n} ({k['title']}) on {d}? Give GitHub handles.",
                       gold=dict(leads=leads_on(d).get(k["sig"], [])), kep=f"KEP-{n}", date=d))
    # (3) was KEP-X in force on date D, and if not, what retired it
    pool = sorted(K)
    for n in pick(pool, PER_TEMPLATE, "t3"):
        k = K[n]
        d = a_date("t3" + n)
        st = status_on(k, d)
        in_force = st in IN_FORCE
        retired = None if in_force or st not in ("withdrawn", "replaced", "deferred") else (successor(k, K) or st)
        qs.append(dict(template=3, question=f"Was KEP-{n} ({k['title']}) in force on {d}? If not, what retired it (the replacing KEP, or 'withdrawn' / 'deferred')?",
                       gold=dict(in_force=in_force, retired_by=retired), kep=f"KEP-{n}", date=d))
    # (4) who wrote KEP-X, and is each of them a SIG chair or tech lead today
    now = leads_on(TODAY)
    lead_now = {x for v in now.values() for x in v}
    pool = [n for n, k in K.items() if k["authors"]]
    for n in pick(pool, PER_TEMPLATE, "t4"):
        k = K[n]
        qs.append(dict(template=4, question=f"Who are the authors of KEP-{n} ({k['title']}), and is each of them a chair or tech lead of any SIG as of {TODAY}? Give GitHub handles.",
                       gold=dict(authors=sorted([a, a in lead_now] for a in k["authors"])), kep=f"KEP-{n}"))
    if STUDY == "k2":
        # (5) how many of a SIG's KEPs were in force on a date
        for i, sig in enumerate(pick([s for s in SIGS for _ in range(4)], PER_TEMPLATE, "t5")):
            d = a_date(f"t5{sig}{i}")
            n = sum(1 for k in K.values() if k["sig"] == sig and status_on(k, d) in IN_FORCE)
            qs.append(dict(template=5, question=f"How many KEPs owned by {sig} were in force (implementable or implemented) on {d}?",
                           gold=dict(count=n), sig=sig, date=d))
        # (6) was a person a lead of the SIG that owns KEP-X on the day it was created
        pool = [n for n, k in K.items() if k["sig"] in SIGS and k.get("created")]
        for j, n in enumerate(pick(pool, PER_TEMPLATE, "t6")):
            k = K[n]
            then = leads_on(k["created"]).get(k["sig"], [])
            other = sorted({x for v in leads_on(a_date("t6o" + n)).values() for x in v} - set(then))
            who = (then if (then and int(h("t6p" + n), 16) % 2 == 0) or not other else other)
            p = sorted(who)[int(h("t6q" + n), 16) % len(who)] if who else None
            if not p:
                continue
            qs.append(dict(template=6, question=f"Was {p} a chair or tech lead of the SIG that owns KEP-{n} ({k['title']}) on the day KEP-{n} was created ({k['created']})?",
                           gold=dict(was_lead=p in then), kep=f"KEP-{n}", person=p, date=k["created"]))
    for q in qs:
        q["id"] = f"{STUDY}-" + h(q["question"])[:10]
    by_t = {}
    for q in qs:
        by_t.setdefault(q["template"], []).append(q)
    for t, xs in by_t.items():
        xs.sort(key=lambda q: q["id"])
        k = round(len(xs) * 0.3)
        for i, q in enumerate(sorted(xs, key=lambda q: h(q["id"]))):
            q["split"] = "dev" if i < k else "test"
    body = dict(today=TODAY, sigs=list(SIGS), questions=sorted(qs, key=lambda q: (q["template"], q["id"])))
    digest = h(json.dumps(body, sort_keys=True))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dict(sha256=digest, **body), indent=1) + "\n")
    print(f"K1: {len(qs)} questions ({', '.join(f't{t}: {len(v)}' for t, v in sorted(by_t.items()))}); "
          f"test {sum(q['split'] == 'test' for q in qs)}; sha256 {digest}")


if __name__ == "__main__":
    main()
