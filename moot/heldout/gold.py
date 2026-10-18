"""The answer key for study H1, written by the repositories, not by us.

Unit: one decision whose ADR title picks an outside tool (the backtest's catalogue, moot/backtest/tools.py), in force on the
cut date T0 and already committed to its repository by then. The question every arm answers, seeing only what existed on T0: does this decision still hold?

Gold, from three independent sources, all dated after T0 and on or before END:
  status    the repository marked the ADR superseded, deprecated, invalidated or similar, moved it to an archive folder,
            or a later ADR titled itself as dropping the tool (moot/backtest/labels.py, the backtest's own key)
  code      the tool was in the repository's dependency manifests or Terraform on T0 and is gone at END
  DEAD      either of the above;  HOLDS   neither, and the ADR is still in force at END
Each HOLDS says what backs it: `code` (the tool is still in the code at END) or `status` (no code signal for this tool in
this repository, so only the ADR's unchanged status says it holds). A decision whose ADR file was deleted without a status
change is left out: deleting a file is not a statement either way.

The split is frozen here: within each gold class, units sorted by sha256(id) and the first 30% go to dev, the rest to test.
gold.json carries its own sha256 over (T0, END, units, labels, split); eval/eval_heldout.py refuses to score if it changes.

  python3 -m moot.heldout.gold --mine     clone and parse the new repositories (moot/heldout/tools.py), tag tools, then label
  python3 -m moot.heldout.gold --tag      re-tag data/heldout/new_raw.json, then label
  python3 -m moot.heldout.gold            label only (needs the clones in data/backtest/.repos; make backtest clones them)
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import date, timedelta
from pathlib import Path

from ..backtest.code import BASENAMES as BT_BASENAMES
from ..backtest.labels import REPOS_DIR, clone, decide, git, mine
from ..backtest.tools import DEPENDENCY as BT_DEPENDENCY, NOT_PICKED, TOOLS as BT_TOOLS
from .tools import DROPPING, EXTRA_DEPENDENCY, EXTRA_INFRA, EXTRA_MANIFESTS, EXTRA_TOOLS, NEW_REPOS

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "heldout"
GOLD = ROOT / "eval" / "heldout" / "gold.json"
T0 = "2023-10-17"   # three years before END; see docs/studies.md H1 for why this date
END = "2026-10-17"  # the backtest's snapshot date
DEV_SHARE = 0.3

# Tools that live in Terraform or Kubernetes config rather than a package manifest: (file pattern, content pattern or None)
INFRA = {
    "terraform": (r"\.tf$", None),
    "puppet": (r"\.pp$", None),
    "helm": (r"\.tf$", r"\bhelm_release\b"),
    "tf-aws-eks": (r"\.tf$", r"terraform-aws-modules/eks/aws"),
    "aws-lbc": (r"\.tf$", r"aws-load-balancer-controller"),
    "external-dns": (r"\.tf$", r"external-dns"),
    "external-secrets": (r"\.tf$", r"external-secrets"),
    "argocd": (r"\.tf$", r"argo-cd|argocd"),
    "prometheus-adapter": (r"\.tf$", r"prometheus-adapter"),
    "crossplane": (r"\.tf$", r"crossplane"),
    "gatekeeper": (r"\.tf$", r"gatekeeper"),
    "karpenter": (r"\.tf$", r"karpenter"),
    "fluent-bit": (r"\.tf$", r"fluent-bit"),
    "opensearch": (r"\.tf$", r"aws_opensearch_domain"),
    "elasticsearch": (r"\.tf$", r"aws_elasticsearch_domain"),
    "redis": (r"\.tf$", r"aws_elasticache_(replication_group|cluster)"),
    "mongodb": (r"\.tf$", r"aws_docdb_cluster|mongodb"),
    "istio": (r"\.tf$", r"\bistio"),
    "concourse": (r"\.tf$", r"concourse"),
    "consul": (r"\.tf$", r"\bconsul\b"),
}
INFRA.update(EXTRA_INFRA)
DEPENDENCY = {**BT_DEPENDENCY, **EXTRA_DEPENDENCY}
BASENAMES = BT_BASENAMES | set(EXTRA_MANIFESTS)
TOOLS = {**BT_TOOLS, **EXTRA_TOOLS}
MAX_FILES = 3000


def rev_at(repo: Path, day: str) -> str | None:
    return git(repo, "rev-list", "-1", f"--before={day}T23:59:59", "HEAD").strip() or None


def _prefetch(repo: Path, rev: str, paths: list[str]) -> None:
    """A blob-less clone fetches a missing blob one round trip at a time; ask for every missing one in a single fetch."""
    want = set(paths)
    oids = [l.split()[2] for l in git(repo, "ls-tree", "-r", rev).splitlines() if l.split("\t", 1)[-1] in want]
    if not oids:
        return
    env = dict(__import__("os").environ, GIT_NO_LAZY_FETCH="1")
    check = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch-check"], input="\n".join(oids) + "\n",
                           capture_output=True, text=True, env=env).stdout
    missing = [l.split()[0] for l in check.splitlines() if l.endswith("missing")]
    if missing:
        subprocess.run(["git", "-C", str(repo), "-c", "fetch.negotiationAlgorithm=noop", "fetch", "-q", "origin", "--no-tags",
                        "--no-write-fetch-head", "--recurse-submodules=no", "--filter=blob:none", "--stdin"],
                       input="\n".join(missing) + "\n", capture_output=True, text=True)


def _read(repo: Path, rev: str, paths: list[str]) -> dict[str, str]:
    if not paths:
        return {}
    _prefetch(repo, rev, paths)
    blob = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"], capture_output=True,
                          input="".join(f"{rev}:{p}\n" for p in paths).encode()).stdout
    out, pos = {}, 0
    for p in paths:
        nl = blob.index(b"\n", pos)
        hdr = blob[pos:nl].decode(errors="replace")
        pos = nl + 1
        if hdr.endswith("missing"):
            continue
        size = int(hdr.split()[-1])
        out[p] = blob[pos:pos + size].decode("utf-8", "replace")
        pos += size + 1
    return out


_tree_cache: dict = {}


def tree(repo: Path, rev: str) -> list[str]:
    k = (str(repo), rev)
    if k not in _tree_cache:
        _tree_cache[k] = git(repo, "ls-tree", "-r", "--name-only", rev).splitlines()
    return _tree_cache[k]


def in_code(repo: Path, rev: str, tool: str) -> bool | None:
    """True / False when the tool is visible (or not) in the code at rev; None when this tool has no code signal here."""
    names = tree(repo, rev)
    if tool in DEPENDENCY:
        man = [p for p in names if p.rsplit("/", 1)[-1] in BASENAMES and p.count("/") <= 3
               and not re.search(r"node_modules|fixture|test|example", p)]
        texts = _read(repo, rev, man)
        return any(re.search(DEPENDENCY[tool], t) for t in texts.values()) if texts else None
    if tool in INFRA:
        fpat, cpat = INFRA[tool]
        files = [p for p in names if re.search(fpat, p) and not re.search(r"(^|/)(test|tests|examples?|fixtures?)/", p)]
        if not files:
            return None  # no Terraform (or Puppet) here at all: the code says nothing about this tool
        if cpat is None:
            return True
        return any(re.search(cpat, t, re.I) for t in _read(repo, rev, files[:MAX_FILES]).values())
    return None


def removal_date(repo: Path, tool: str, after: str, end: str) -> str | None:
    """The first month start after `after` on which the tool is no longer in the code, found by bisection over month starts
    (present on `after`, gone on `end`; a tool that left and came back is dated by its last departure the search finds)."""
    d = date.fromisoformat(after).replace(day=1)
    months = []
    while True:
        d = (d + timedelta(days=32)).replace(day=1)
        if d.isoformat() > end:
            break
        months.append(d.isoformat())
    lo, hi = -1, len(months)  # months[lo] present (or `after`), months[hi] gone (or `end`)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        r = rev_at(repo, months[mid])
        if r and in_code(repo, r, tool):
            lo = mid
        else:
            hi = mid
    return months[hi] if hi < len(months) else end


def in_force(d: dict, day: str) -> bool:
    return d["born"] <= day and not (d["death"] and d["death"]["date"] <= day) and not (d["deleted"] and d["deleted"] <= day)


def label(d: dict) -> dict | None:
    repo = REPOS_DIR / d["repo"].replace("/", "__")
    r0, r1 = rev_at(repo, T0), rev_at(repo, END)
    code0 = {t: in_code(repo, r0, t) for t in d["tools"]} if r0 else {}
    code1 = {t: in_code(repo, r1, t) for t in d["tools"]} if r1 else {}
    events = []
    if d["death"] and T0 < d["death"]["date"] <= END:
        events.append(dict(source="status", date=d["death"]["date"], what=f"{d['death']['kind']}: {d['death']['quote'][:160]}"))
    for t in d["tools"]:
        if code0.get(t) and not code1.get(t):  # in the code on T0, gone (or its manifests gone) at END
            when = removal_date(repo, t, T0, END) or END
            events.append(dict(source="code", date=when, what=f"{t} is in the code on {T0} and gone by {when}"))
    if events:
        first = min(events, key=lambda e: e["date"])
        return dict(gold="DEAD", backed_by=sorted({e["source"] for e in events}), first=first, events=events, code_t0=code0, code_end=code1)
    if d["deleted"] and T0 < d["deleted"] <= END:
        return None  # the file went away with no statement either way
    if any(code1.get(t) for t in d["tools"]):
        return dict(gold="HOLDS", backed_by=["code"], code_t0=code0, code_end=code1)
    if all(code0.get(t) is None for t in d["tools"]):
        return dict(gold="HOLDS", backed_by=["status"], code_t0=code0, code_end=code1)
    return None  # the tool was not in the code on T0, so the code cannot say whether the decision still governs it


def mine_new() -> None:
    """Every ADR in the new repositories, through the backtest's own parser (moot/backtest/labels.py) -> data/heldout/new_raw.json."""
    raw = []
    for name in NEW_REPOS:
        clone(name)
        raw += [d for d in (decide(r) for r in mine(name)) if d]
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "new_raw.json").write_text(json.dumps(raw, indent=1) + "\n")


def tag_new() -> None:
    """data/heldout/new_raw.json -> data/heldout/new_decisions.json (see tag)."""
    (DATA / "new_decisions.json").write_text(json.dumps(tag(json.loads((DATA / "new_raw.json").read_text())), indent=1) + "\n")


def tag(raw: list[dict]) -> list[dict]:
    """Which tool each ADR's title picks (catalogue + EXTRA_TOOLS, minus tools it drops), and the deaths a later ADR's title
    implies, as the backtest does with NOT_PICKED."""
    out = []
    for d in raw:
        named = {t for t, (_, rx, _) in TOOLS.items() if re.search(rx, d["title"], re.I)}
        drop = {t for t in named if re.search(DROPPING + "(?:" + TOOLS[t][1] + ")", d["title"], re.I)}
        drop |= set().union(*[v for rx, v in NOT_PICKED.items() if re.search(rx, d["title"], re.I)]) & named
        d = dict(d, tools=sorted(named - drop), dropped=sorted(drop))
        out.append(d)
    for d in out:
        for t in d["tools"]:
            for later in out:
                if later["repo"] == d["repo"] and later["born"] > d["born"] and t in later["dropped"] \
                        and (not d["death"] or later["born"] < d["death"]["date"]):
                    d["death"] = dict(date=later["born"], kind="replaced", quote=later["title"], commit=None, path=later["path"])
    return sorted(out, key=lambda d: d["id"])


def units() -> list[dict]:
    bt = json.loads((ROOT / "data" / "backtest" / "decisions.json").read_text())
    new = json.loads((DATA / "new_decisions.json").read_text()) if (DATA / "new_decisions.json").exists() else []
    for d in bt:
        d["source"] = "backtest"
    for d in new:
        d["source"] = "new"
    # the ADR must have been in the repository on T0, not only dated before it (imported ADRs carry an older own date)
    return [d for d in bt + new if d["tools"] and in_force(d, T0) and d["first_commit"] <= T0]


def digest(payload: dict) -> str:
    body = {k: payload[k] for k in ("t0", "end", "units")}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def main() -> None:
    out, skipped = [], []
    for d in units():
        g = label(d)
        if g is None:
            skipped.append(d["id"])
            continue
        out.append(dict(id=d["id"], repo=d["repo"], source=d["source"], title=d["title"], path=d["path"], url=d["url"], born=d["born"],
                        tools=d["tools"], **g))
    for cls in ("DEAD", "HOLDS"):
        xs = sorted((u for u in out if u["gold"] == cls), key=lambda u: hashlib.sha256(u["id"].encode()).hexdigest())
        k = round(len(xs) * DEV_SHARE)
        for i, u in enumerate(xs):
            u["split"] = "dev" if i < k else "test"
    out.sort(key=lambda u: u["id"])
    payload = dict(t0=T0, end=END, units=out)
    payload = dict(sha256=digest(payload), written=date.today().isoformat(), skipped=sorted(skipped), **payload)
    GOLD.parent.mkdir(parents=True, exist_ok=True)
    GOLD.write_text(json.dumps(payload, indent=1) + "\n")
    c = lambda **kw: sum(1 for u in out if all(u.get(k) == v for k, v in kw.items()))
    print(f"T0 {T0}: {len(out)} units ({len(skipped)} left out); DEAD {c(gold='DEAD')} (dev {c(gold='DEAD', split='dev')}), "
          f"HOLDS {c(gold='HOLDS')} (dev {c(gold='HOLDS', split='dev')}); new repos {c(source='new')}; sha256 {payload['sha256'][:16]}")


if __name__ == "__main__":
    import sys
    if "--mine" in sys.argv:
        mine_new()
    if "--mine" in sys.argv or "--tag" in sys.argv:
        tag_new()
    main()
