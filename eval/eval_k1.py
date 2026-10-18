"""Study K1: questions about Kubernetes as an organisation, answered by agents with different tools (docs/studies.md K1).

Questions and gold: eval/k1/questions.json (moot/k1.py), pinned in eval/k1/QUESTIONS.sha256; this script refuses to score if
either changes. Every model arm uses the same local model (qwen3.8:27b through Ollama, temperature 0, JSON replies).

  moot_tools    an agent whose tools are Moot's read-only graph queries on graph gh_kubernetes_enhancements
  file_tools    an agent whose tools read the same two checkouts: list files, read a file at a revision, grep the KEP files and
                sigs.yaml, git log of a path
  rag_bm25      BM25 top 5 over the checkouts' files at HEAD (kep.yaml files, KEP summaries, one block per SIG of sigs.yaml)
  moot_direct   no model: each template answered by one fixed graph query (the shared-source reference, not a contest)

  python3 eval/eval_k1.py --llm [--split dev]      fill the model caches (eval/k1/cache.jsonl), then score
  python3 eval/eval_k1.py                          score from the caches -> eval/results_k1.{md,json}
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from rank_bm25 import BM25Okapi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from moot import tools  # noqa: E402
from moot.graph import graph  # noqa: E402
from moot.stats import wilson  # noqa: E402

OUT = Path(os.getenv("MOOT_EVAL_OUT") or ROOT / "eval")
K = ROOT / "eval" / "k1"
Q = json.loads((K / "questions.json").read_text())
PINNED = (K / "QUESTIONS.sha256").read_text().split()[0] if (K / "QUESTIONS.sha256").exists() else None
CACHE = K / "cache.jsonl"
MODEL = os.getenv("MOOT_K1_MODEL", "qwen3.8:27b")
OLLAMA = os.getenv("OLLAMA_URL", "http://localhost:11434")
ENH = ROOT / "data" / "github" / ".repos" / "kubernetes__enhancements"
COM = ROOT / "data" / "github" / ".repos" / "kubernetes__community"
REPOS = {"enhancements": ENH, "community": COM}
GRAPH = "gh_kubernetes_enhancements"
ARMS = ("moot_tools", "file_tools", "rag_bm25", "moot_direct")
MAX_STEPS = 8


def refuse_if_changed() -> None:
    body = {k: v for k, v in Q.items() if k != "sha256"}
    now = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    if now != Q["sha256"] or now != PINNED:
        sys.exit(f"K1 questions changed: {now[:16]} vs pinned {str(PINNED)[:16]}; refusing to score")


FORMATS = {1: '{"kep": "KEP-<number>", "date": "YYYY-MM-DD"}', 2: '{"leads": ["<github handle>", ...]}',
           3: '{"in_force": true or false, "retired_by": "KEP-<number>" or "withdrawn" or "deferred" or null}',
           4: '{"authors": [["<github handle>", true or false], ...]}'}


def norm(t: int, a) -> object:
    if not isinstance(a, dict):
        return None
    try:
        if t == 1:
            return (str(a.get("kep", "")).upper().replace(" ", ""), str(a.get("date", ""))[:10])
        if t == 2:
            return tuple(sorted({str(x).lower().lstrip("@") for x in a.get("leads") or []}))
        if t == 3:
            rb = a.get("retired_by")
            return (bool(a.get("in_force")), (str(rb).upper().replace(" ", "") if rb and str(rb).upper().startswith("KEP") else (str(rb).lower() if rb else None)))
        if t == 4:
            return tuple(sorted((str(x[0]).lower().lstrip("@"), bool(x[1])) for x in a.get("authors") or []))
    except Exception:
        return None


def right(q: dict, a) -> bool:
    return a is not None and norm(q["template"], a) == norm(q["template"], q["gold"])


# ---- the model

def chat(messages: list[dict]) -> tuple[str, int, int, float]:
    body = dict(model=MODEL, stream=False, think=False, format="json", options=dict(temperature=0, seed=7, num_ctx=16384), messages=messages)
    t0 = time.perf_counter()
    for attempt in range(4):
        try:
            r = json.loads(urllib.request.urlopen(urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(body).encode(),
                                                                        headers={"content-type": "application/json"}), timeout=1200).read())
            return r["message"]["content"], r.get("prompt_eval_count", 0), r.get("eval_count", 0), time.perf_counter() - t0
        except Exception:
            if attempt == 3:
                raise
            time.sleep(10)
    raise RuntimeError


SYSTEM = """You answer questions about the Kubernetes project's enhancement proposals (KEPs) and its SIGs. Use the tools to find \
facts; never answer from memory. Each reply is one JSON object: either {"tool": "<name>", "args": {...}} to call a tool, or \
{"answer": <the answer in the requested format>} to finish. At most %d tool calls.""" % MAX_STEPS


def agent(q: dict, tool_doc: str, run) -> dict:
    msgs = [dict(role="system", content=SYSTEM + "\nTools:\n" + tool_doc),
            dict(role="user", content=f"{q['question']}\nAnswer format: {FORMATS[q['template']]}")]
    tin = tout = calls = 0
    secs = 0.0
    for step in range(MAX_STEPS + 2):
        reply, i, o, s = chat(msgs)
        tin, tout, secs = tin + i, tout + o, secs + s
        try:
            x = json.loads(reply)
        except json.JSONDecodeError:
            x = {}
        if "answer" in x:
            return dict(answer=x["answer"], tokens_in=tin, tokens_out=tout, seconds=round(secs, 1), calls=calls)
        if x.get("tool") and calls < MAX_STEPS:
            calls += 1
            try:
                res = run(str(x["tool"]), x.get("args") or {})
            except Exception as ex:
                res = f"error: {ex}"
            msgs += [dict(role="assistant", content=reply), dict(role="user", content=f"Result of {x['tool']}:\n{str(res)[:6000]}")]
            continue
        msgs += [dict(role="assistant", content=reply or "{}"), dict(role="user", content='Reply now with {"answer": ...} in the requested format.')]
    return dict(answer=None, tokens_in=tin, tokens_out=tout, seconds=round(secs, 1), calls=calls)


# ---- Moot's graph tools

G = None


def moot_run(name: str, a: dict):
    kid = str(a.get("kep") or a.get("id") or "").upper().replace(" ", "")
    if kid and not kid.startswith("KEP-"):
        kid = "KEP-" + re.sub(r"\D", "", kid)
    day = str(a.get("date") or a.get("as_of") or tools.today())[:10]
    if name == "find_kep":
        return json.dumps(tools.find_decision(G, str(a.get("query", ""))))
    if name == "audit_kep":
        x = tools.audit_decision(G, kid, day, 4)
        if not x.get("found"):
            return "not in the graph"
        return json.dumps(dict(verdict=x["verdict"], decision=x["decision"], superseded_by=x["superseded_by"], as_of=day,
                               team=x.get("team"), owner=x.get("owner")), default=str)
    if name == "kep_history":
        return json.dumps(tools.verdict_history(G, kid, day, 4), default=str)
    if name == "team_on":
        return json.dumps(tools.decision_team(G, kid, day), default=str)
    if name == "kep_authors":
        return json.dumps(tools.decision_authors(G, kid, day), default=str)
    return "unknown tool"


MOOT_DOC = """- find_kep(query): KEPs whose title matches
- audit_kep(kep, date): the KEP as of a date: verdict (HOLDS, MOOT, RETIRED, NOT_YET...), what superseded or retired it and when, the team that answers for it and its leads then
- kep_history(kep, date): every verdict the KEP has had and the date each began, up to the date
- team_on(kep, date): the SIG that answers for the KEP and its chairs and tech leads on that date (ids are u_<github handle>), and former leads
- kep_authors(kep, date): the KEP's authors (ids u_<github handle>) and which SIG each leads on that date"""


# ---- file tools over the same checkouts

def _rev(d: Path) -> str:
    from moot.k1 import head_rev
    return head_rev(d)


def file_run(name: str, a: dict):
    repo = REPOS.get(str(a.get("repo", "enhancements")), ENH)
    git = lambda *x: subprocess.run(["git", "-C", str(repo), *x], capture_output=True, text=True, errors="replace").stdout
    rev = str(a.get("rev") or _rev(repo))
    if name == "list_files":
        pre = str(a.get("prefix", ""))
        return "\n".join(f for f in git("ls-tree", "-r", "--name-only", rev).splitlines() if f.startswith(pre))[:6000]
    if name == "read_file":
        return git("cat-file", "-p", f"{rev}:{a.get('path', '')}")[:6000] or "no such file"
    if name == "grep":
        pat, pre = str(a.get("pattern", "")), str(a.get("prefix", "keps/" if repo == ENH else "sigs.yaml"))
        files = [f for f in git("ls-tree", "-r", "--name-only", rev).splitlines() if f.startswith(pre) and (f.endswith("kep.yaml") or f == "sigs.yaml")]
        out = []
        for f in files:
            for i, line in enumerate(git("cat-file", "-p", f"{rev}:{f}").splitlines()):
                if re.search(pat, line, re.I):
                    out.append(f"{f}:{i + 1}: {line.strip()}")
            if len(out) > 80:
                break
        return "\n".join(out[:80]) or "no match"
    if name == "git_log":
        return git("log", "--format=%H %cs %s", "-n", "40", rev, "--", str(a.get("path", "")))[:6000] or "no commits"
    return "unknown tool"


FILE_DOC = """- list_files(repo, prefix): file paths under a prefix; repo is "enhancements" (kubernetes/enhancements) or "community" (kubernetes/community)
- read_file(repo, path, rev): a file's text at a commit (rev defaults to the latest)
- grep(repo, pattern, prefix): lines matching a regex in kep.yaml files under a prefix (enhancements) or in sigs.yaml (community)
- git_log(repo, path): the commits that changed a path, newest first (hash, date, subject)"""


# ---- retrieval

def rag_pool() -> list[dict]:
    enh_rev, com_rev = _rev(ENH), _rev(COM)
    g = lambda d, *x: subprocess.run(["git", "-C", str(d), *x], capture_output=True, text=True, errors="replace").stdout
    pool = []
    for f in g(ENH, "ls-tree", "-r", "--name-only", enh_rev).splitlines():
        if f.split("/")[1:2] and f.split("/")[1] in Q["sigs"] and f.endswith("kep.yaml"):
            pool.append(dict(id=f, text=g(ENH, "cat-file", "-p", f"{enh_rev}:{f}")[:3000]))
    sigs = g(COM, "cat-file", "-p", f"{com_rev}:sigs.yaml")
    for block in re.split(r"\n  - dir: ", sigs):
        pool.append(dict(id="sigs.yaml:" + block.split("\n", 1)[0][:30], text=block[:3000]))
    return pool


POOL = None


def rag(q: dict) -> dict:
    global POOL
    POOL = POOL or rag_pool()
    tok = lambda s: re.findall(r"[a-z0-9]+", s.lower())
    bm = BM25Okapi([tok(p["text"]) for p in POOL])
    sc = bm.get_scores(tok(q["question"]))
    top = [POOL[i] for i in sorted(range(len(POOL)), key=lambda i: -sc[i])[:5]]
    ctx = "\n\n".join(f"[{p['id']}]\n{p['text']}" for p in top)
    reply, i, o, s = chat([dict(role="system", content="Answer from the context only. Reply with one JSON object: {\"answer\": <the answer in the requested format>}."),
                           dict(role="user", content=f"{q['question']}\nAnswer format: {FORMATS[q['template']]}\n\nContext:\n{ctx}")])
    try:
        ans = json.loads(reply).get("answer")
    except json.JSONDecodeError:
        ans = None
    return dict(answer=ans, tokens_in=i, tokens_out=o, seconds=round(s, 1), calls=0)


# ---- deterministic reference

def direct(q: dict):
    t, kid = q["template"], q["kep"]
    if t == 1:
        a = tools.audit_decision(G, kid, tools.today(), 4)
        s = (a.get("superseded_by") or {}) if a.get("found") else {}
        return dict(kep=s.get("id"), date=s.get("at"))
    if t == 2:
        team = tools.decision_team(G, kid, q["date"])
        return dict(leads=[x["id"].removeprefix("u_") for x in (team or {}).get("leads", [])])
    if t == 3:
        a = tools.audit_decision(G, kid, q["date"], 4)
        if not a.get("found") or a["verdict"] in ("NOT_YET",):
            return dict(in_force=False, retired_by=None)
        if a["verdict"] == "RETIRED":
            s = a["superseded_by"]
            word = (s.get("quote") or "").replace("status:", "").strip() if s.get("kind") == "document" else None
            return dict(in_force=False, retired_by=s["id"] if s.get("kind") == "decision" else (word or None))
        return dict(in_force=True, retired_by=None)
    if t == 4:
        return dict(authors=[[x["id"].removeprefix("u_"), bool(x["leads"])] for x in tools.decision_authors(G, kid, Q["today"])])


def cached(arm: str, q: dict, fill: bool, cache: dict) -> dict | None:
    key = hashlib.sha256(json.dumps([arm, MODEL, q["id"], SYSTEM, MOOT_DOC if arm == "moot_tools" else FILE_DOC]).encode()).hexdigest()[:20]
    if key in cache:
        return cache[key]
    if not fill:
        return None
    r = agent(q, MOOT_DOC, moot_run) if arm == "moot_tools" else agent(q, FILE_DOC, file_run) if arm == "file_tools" else rag(q)
    row = dict(key=key, arm=arm, id=q["id"], **r)
    with CACHE.open("a") as f:
        f.write(json.dumps(row) + "\n")
    cache[key] = row
    print(arm, q["id"], "right" if right(q, r["answer"]) else "wrong", flush=True)
    return row


def main() -> None:
    global G
    refuse_if_changed()
    G = graph(GRAPH)
    fill = "--llm" in sys.argv
    only = sys.argv[sys.argv.index("--split") + 1] if "--split" in sys.argv else None
    cache = {}
    if CACHE.exists():
        cache = {r["key"]: r for r in (json.loads(l) for l in CACHE.read_text().splitlines() if l.strip())}
    rows = []
    for q in Q["questions"]:
        r = dict(id=q["id"], template=q["template"], split=q["split"])
        r["moot_direct"] = right(q, direct(q))
        for arm in ("moot_tools", "file_tools", "rag_bm25"):
            c = cached(arm, q, fill and (only is None or q["split"] == only), cache)
            r[arm] = right(q, c["answer"]) if c else None
            if c:
                r[arm + "_cost"] = dict(tokens_in=c["tokens_in"], tokens_out=c["tokens_out"], seconds=c["seconds"], calls=c["calls"])
        rows.append(r)
    res = {}
    for split in ("test", "dev"):
        rs = [r for r in rows if r["split"] == split]
        res[split] = {}
        for arm in ARMS:
            got = [r for r in rs if r[arm] is not None]
            k = sum(r[arm] for r in got)
            per = {t: f"{sum(r[arm] for r in got if r['template'] == t)}/{sum(1 for r in got if r['template'] == t)}" for t in (1, 2, 3, 4)}
            costs = [r[arm + "_cost"] for r in got if arm + "_cost" in r]
            res[split][arm] = dict(right=k, n=len(got), of=len(rs), ci=wilson(k, len(got)), per_template=per,
                                   tokens=sum(c["tokens_in"] + c["tokens_out"] for c in costs),
                                   seconds_median=sorted(c["seconds"] for c in costs)[len(costs) // 2] if costs else None,
                                   calls=sum(c["calls"] for c in costs))
    (OUT / "results_k1.json").write_text(json.dumps(dict(model=MODEL, questions_sha256=Q["sha256"], results=res, rows=rows), indent=1) + "\n")
    names = dict(moot_tools="**agent with Moot's graph tools**", file_tools="agent with file and git tools over the same checkouts",
                 rag_bm25="BM25 RAG over the checkouts at HEAD", moot_direct="Moot, one fixed graph query per template, no model (shared-source reference)")
    L = ["# K1: questions about Kubernetes as an organisation (study K1)", "",
         f"{len(Q['questions'])} templated questions about SIG Auth and SIG Node KEPs; gold from the raw git history of kubernetes/enhancements and "
         f"kubernetes/community (`moot/k1.py`), hashed before any arm ran (`{Q['sha256'][:16]}…`). Same local model ({MODEL}, temperature 0) for every "
         "model arm. **Shared-source caveat:** Moot's graph is built from the same files, so its fixed-query row is close to the gold by construction; "
         "the contest is between agents with the same model and different tools. Templates: (1) which KEP replaced it and when, (2) who led its SIG "
         "on a date, (3) was it in force on a date and what retired it, (4) its authors and whether each leads a SIG today.", ""]
    for split in ("test", "dev"):
        L += [f"## {split.title()} split", "", "| arm | exact match (95% CI) | t1 | t2 | t3 | t4 | tokens | median s per question | tool calls |",
              "|---|---|---|---|---|---|---|---|---|"]
        for arm in ARMS:
            s = res[split][arm]
            if not s["n"]:
                continue
            L.append(f"| {names[arm]} | {s['right']}/{s['n']} ({s['ci'][0]:.2f}–{s['ci'][1]:.2f}) | " + " | ".join(s["per_template"][t] for t in (1, 2, 3, 4))
                     + f" | {s['tokens']:,} | {s['seconds_median'] if s['seconds_median'] is not None else '–'} | {s['calls']} |")
        L.append("")
    (OUT / "results_k1.md").write_text("\n".join(L) + "\n")
    t = res["test"]
    print("test: " + ", ".join(f"{a} {t[a]['right']}/{t[a]['n']}" for a in ARMS))


if __name__ == "__main__":
    main()
