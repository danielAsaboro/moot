"""Connector: Kubernetes Enhancement Proposals (KEPs) as a company's decisions, with their SIGs as the teams that own them.

  moot ingest-keps [--sig sig-auth --sig sig-node] [--no-model]

Kubernetes runs on written decisions: every KEP in github.com/kubernetes/enhancements has a kep.yaml (status, authors,
owning and participating SIGs, replaces / superseded-by) and a README whose Summary and Motivation say why. What it reads
(a blob-less clone in data/github/.repos):
  each KEP         kep.yaml at HEAD, and its history: the commit that first made it implementable (when it came into force)
                   and the commit that marked it withdrawn, replaced or deferred (a dated RETIRES, with the PR from "(#123)")
  replaces         a SUPERSEDES edge from the newer KEP, dated on the commit that retired the older one, or the newer KEP's date
  its people       the authors and approvers in kep.yaml, by GitHub handle (the first author owns it); they know why
  its SIGs         the owning and participating SIGs, as the Systems the decision governs
  stated reasons   read from the Summary, Motivation and Goals by a model and kept only as literal quoted spans
                   (moot/connectors/reasons.py, cached in data/github/kubernetes__enhancements/reasons.json); each later KEP is
                   judged against earlier reasons as dated SUPPORTS / CONTRADICTS evidence, exactly as for ADRs
Writes data/github/kubernetes__enhancements/{graph.json,summary.json} and seeds graph `gh_kubernetes_enhancements`.
A provisional or rejected KEP was never in force and is left out.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import date
from pathlib import Path

import yaml

from . import github as gh
from . import reasons as rsn
from . import teams as tm

REPO = "kubernetes/enhancements"
DEFAULT_SIGS = ["sig-auth"]
IN_FORCE = {"implementable", "implemented"}
GONE = {"withdrawn", "replaced", "deferred"}
SIG_NAMES = {"sig-auth": "SIG Auth", "sig-node": "SIG Node", "sig-api-machinery": "SIG API Machinery", "sig-storage": "SIG Storage",
             "sig-network": "SIG Network", "sig-apps": "SIG Apps", "sig-cli": "SIG CLI", "sig-scheduling": "SIG Scheduling",
             "sig-cluster-lifecycle": "SIG Cluster Lifecycle", "sig-cloud-provider": "SIG Cloud Provider", "sig-instrumentation": "SIG Instrumentation",
             "sig-architecture": "SIG Architecture", "sig-release": "SIG Release", "sig-windows": "SIG Windows", "sig-autoscaling": "SIG Autoscaling",
             "sig-testing": "SIG Testing", "sig-security": "SIG Security", "sig-multicluster": "SIG Multicluster", "sig-etcd": "SIG etcd"}
KEEP_SECTIONS = re.compile(r"^#{1,3}\s*(summary|motivation|goals|non-goals|user stories)\b", re.I)


def git(d: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True, errors="replace").stdout


def show_many(d: Path, specs: list[str]) -> list[str]:
    """`git show` of many rev:path blobs in one cat-file call (one fetch for a blob-less clone)."""
    if not specs:
        return []
    blob = subprocess.run(["git", "-C", str(d), "cat-file", "--batch"], capture_output=True, input="".join(s + "\n" for s in specs).encode()).stdout
    out, pos = [], 0
    for _ in specs:
        nl = blob.index(b"\n", pos)
        hdr = blob[pos:nl].decode(errors="replace")
        pos = nl + 1
        if hdr.endswith("missing"):
            out.append("")
            continue
        size = int(hdr.split()[-1])
        out.append(blob[pos:pos + size].decode("utf-8", "replace"))
        pos += size + 1
    return out


def why_text(readme: str) -> str:
    """The title line plus the Summary, Motivation, Goals and Non-Goals sections, verbatim (quotes must be spans of this)."""
    lines, keep, out = readme.splitlines(), False, []
    for l in lines:
        h = re.match(r"^(#{1,6})\s", l)
        if h:
            keep = bool(KEEP_SECTIONS.match(l)) or (keep and len(h.group(1)) > 2)
        if keep or (not out and l.startswith("# ")):
            out.append(l)
    return "\n".join(out).strip()


def handle(a) -> str:
    return str(a).strip().lstrip("@").split()[0].lower() if a else ""


def history(d: Path, path: str) -> list[dict]:
    """Every commit to the KEP's kep.yaml, oldest first, with the status it set."""
    log = git(d, "log", "--follow", "--reverse", "--format=%H %cs %an%x09%s", "--", path)
    commits = []
    for line in log.splitlines():
        head, _, subject = line.partition("\t")
        h, day, *who = head.split(" ")
        commits.append(dict(sha=h, date=day, author=" ".join(who), subject=subject))
    names = git(d, "log", "--follow", "--reverse", "--name-only", "--format=@%H", "--", path)
    at, cur = {}, None
    for l in names.splitlines():
        if l.startswith("@"):
            cur = l[1:]
        elif l.strip() and cur:
            at[cur] = l.strip()
    texts = show_many(d, [f"{c['sha']}:{at.get(c['sha'], path)}" for c in commits])
    for c, t in zip(commits, texts):
        try:
            c["status"] = str((yaml.safe_load(t) or {}).get("status", "")).lower()
        except yaml.YAMLError:
            c["status"] = ""
    return commits


def pr_of(subject: str) -> int | None:
    m = re.search(r"\(#(\d+)\)\s*$", subject) or re.search(r"Merge pull request #(\d+)", subject)
    return int(m.group(1)) if m else None


def ingest(sigs: list[str] | None = None, call_model: bool = True, today: str | None = None) -> dict:
    sigs = sigs or DEFAULT_SIGS
    today = today or date.today().isoformat()
    d = gh.clone(REPO)
    files = [f for f in git(d, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
             if f.endswith("/kep.yaml") and f.split("/")[1] in sigs]
    metas = show_many(d, [f"HEAD:{f}" for f in files])
    readmes = show_many(d, [f"HEAD:{f.rsplit('/', 1)[0]}/README.md" for f in files])
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    add = lambda n: nodes.setdefault(n["id"], n)
    decisions, by_num = [], {}
    for f, meta, readme in zip(files, metas, readmes):
        try:
            y = yaml.safe_load(meta) or {}
        except yaml.YAMLError:
            continue
        status = str(y.get("status", "")).lower()
        num = str(y.get("kep-number", "")).strip().strip('"')
        if not num or status in ("provisional", "rejected", ""):
            continue
        hist = history(d, f)
        if not hist:
            continue
        came = next((c for c in hist if c["status"] in IN_FORCE), None)
        if came is None and status in GONE:
            came = hist[0]  # imported already past provisional: in force from its first commit
        if came is None:
            continue
        gone = next((c for c in hist if c["status"] in GONE and c["date"] >= came["date"]), None) if status in GONE else None
        created = str(y.get("creation-date", "")).strip("'\"")[:10]
        did = f"KEP-{num}"
        folder = f.rsplit("/", 1)[0]
        dec = dict(id=did, num=num, title=str(y.get("title", did)).strip(), status=status, stage=str(y.get("stage", "")),
                   decided_on=min(x for x in (created, came["date"]) if x), came=came, gone=gone, folder=folder,
                   url=f"https://github.com/{REPO}/tree/master/{folder}", authors=[handle(a) for a in (y.get("authors") or []) if handle(a)],
                   approvers=[handle(a) for a in (y.get("approvers") or []) if handle(a)],
                   sigs=[s for s in [y.get("owning-sig")] + list(y.get("participating-sigs") or []) if s],
                   replaces=[str(x) for x in (y.get("replaces") or []) if x], superseded_by=[str(x) for x in (y.get("superseded-by") or []) if x],
                   text=why_text(readme), milestone=str(y.get("latest-milestone", "")).strip("'\""))
        decisions.append(dec)
        by_num[num] = dec
    for dec in decisions:
        summary = re.sub(r"\s+", " ", dec["text"].split("\n", 1)[-1])[:400]
        add(dict(label="Decision", id=dec["id"], props=dict(title=f"{dec['id']}: {dec['title']}", summary=summary, decided_on=dec["decided_on"],
                                                           source=dec["url"], repo=REPO, status=f"{dec['status']} ({dec['stage']}, {dec['milestone']})"[:120])))
        src = f"src:{dec['id']}"
        add(dict(label="Evidence", id=src, props=dict(kind="adr", title=f"{dec['id']}: {dec['title']}", date=dec["decided_on"], path=dec["url"],
                                                    excerpt=summary)))
        edges.append(dict(src=dec["id"], rel="RECORDED_IN", dst=src, props={}))
        # who knows why: the authors and the approvers kep.yaml names, by GitHub handle (git author names are not handles)
        knowers = list(dict.fromkeys(dec["authors"] + dec["approvers"]))
        for who in knowers:
            add(dict(label="Person", id=f"u_{who}", props=dict(name=who, role="KEP author" if who in dec["authors"] else "KEP approver",
                                                               joined="", left="")))
            edges.append(dict(src=f"u_{who}", rel="AUTHORED", dst=src, props=dict(role="author" if who in dec["authors"] else "approver")))
        if dec["authors"]:
            edges.append(dict(src=f"u_{dec['authors'][0]}", rel="OWNS", dst=dec["id"],
                              props=dict(valid_from=dec["decided_on"], valid_to="", handed_over_from="")))
        for s in dec["sigs"]:
            add(dict(label="System", id=f"sys_{s}", props=dict(name=SIG_NAMES.get(s, s))))
            edges.append(dict(src=dec["id"], rel="GOVERNS", dst=f"sys_{s}", props={}))
        if dec["gone"]:
            c = dec["gone"]
            n = pr_of(c["subject"])
            eid = f"pr:{n}" if n else f"status:{dec['id']}"
            add(dict(label="Evidence", id=eid, props=dict(kind="pr" if n else "adr", title=c["subject"][:200], date=c["date"],
                                                        path=f"https://github.com/{REPO}/pull/{n}" if n else dec["url"], excerpt=f"status: {dec['status']}")))
            edges.append(dict(src=eid, rel="RETIRES", dst=dec["id"], props=dict(at=c["date"], quote=f"status: {dec['status']}")))
    for dec in decisions:  # replaces / superseded-by, both directions, as one dated SUPERSEDES edge each
        for old_num in dec["replaces"]:
            old = by_num.get(re.sub(r"\D", "", old_num))
            if old and old is not dec:
                at = old["gone"]["date"] if old["gone"] else dec["decided_on"]
                edges.append(dict(src=dec["id"], rel="SUPERSEDES", dst=old["id"], props=dict(at=at, quote=f"{dec['id']} replaces {old['id']}")))
        for new_num in dec["superseded_by"]:
            new = by_num.get(re.sub(r"\D", "", new_num))
            if new and new is not dec and dec["id"] not in [re.sub(r"\D", "", x) for x in new["replaces"]]:
                at = dec["gone"]["date"] if dec["gone"] else new["decided_on"]
                edges.append(dict(src=new["id"], rel="SUPERSEDES", dst=dec["id"], props=dict(at=at, quote=f"{dec['id']} superseded by {new['id']}")))
    out = gh.OUT / REPO.replace("/", "__")
    out.mkdir(parents=True, exist_ok=True)
    for dec in decisions:
        dec["text"] = dec["text"][:12000]
    stated = rsn.run(decisions, {}, out / "reasons.json", call_model=call_model)
    by_id = {x["id"]: x for x in decisions}
    for did, rs in stated["reasons"].items():
        for r in rs:
            add(dict(label="Premise", id=r["id"], props=dict(text=r["text"], kind="stated", quote=r["quote"], section=r["section"],
                                                           span=f"{r['span'][0]}-{r['span'][1]}", source=by_id[did]["url"],
                                                           extracted_by=r["model"], decision=did)))
            edges.append(dict(src=did, rel="BECAUSE_OF", dst=r["id"], props=dict(quote=r["quote"][:300], extracted_by=r["model"])))
    for did, rels in stated["relations"].items():
        for r in rels:
            edges.append(dict(src=f"src:{did}", rel=r["rel"], dst=r["reason_id"], props=dict(at=r["at"], quote=r["quote"][:300], why=r["why"],
                                                                                           extracted_by=r["model"])))
    # the SIGs as teams: who leads each one, when, and the decisions it answers for (kubernetes/community sigs.yaml)
    tnodes, tedges = tm.k8s_sigs(gh.clone("kubernetes/community"), None, today)  # every SIG's leadership; KEPs only for `sigs`
    for n in tnodes:
        if n["id"] in nodes and n["label"] == "Person":
            nodes[n["id"]]["props"].update(name=n["props"]["name"], role=n["props"]["role"])
        else:
            add(n)
    edges += tedges
    teams_here = {n["id"] for n in tnodes if n["label"] == "Team"}
    for dec in decisions:
        owning = f"team_{dec['sigs'][0]}" if dec["sigs"] else None
        if owning in teams_here:
            edges.append(dict(src=owning, rel="RESPONSIBLE_FOR", dst=dec["id"], props=dict(valid_from=dec["decided_on"])))
    payload = dict(nodes=list(nodes.values()), edges=edges)
    (out / "graph.json").write_text(json.dumps(payload, indent=1))
    summary = dict(repo=REPO, graph=gh.graph_name(REPO), folder="keps/" + ",".join(sigs), read_on=today, adr_files=len(files),
                   decisions=len(decisions), retired=sum(1 for x in decisions if x["gone"]), sigs=sigs,
                   people=sum(1 for n in nodes.values() if n["label"] == "Person"),
                   pull_requests=sum(1 for n in nodes.values() if n["id"].startswith("pr:")), tools=[], reasons=stated["stats"], checks=0, failing=0)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def audit() -> dict:
    return gh.audit(REPO)


if __name__ == "__main__":
    import sys
    sigs = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--sig=")] or None
    s = ingest(sigs, call_model="--no-model" not in sys.argv)
    print(json.dumps(audit(), indent=1)[:3000])
