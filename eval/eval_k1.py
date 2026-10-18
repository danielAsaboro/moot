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
import urllib.error
import urllib.request
from pathlib import Path

from rank_bm25 import BM25Okapi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from moot import tools  # noqa: E402
from moot.graph import graph  # noqa: E402
from moot.stats import mcnemar_exact, wilson  # noqa: E402
from moot.llm import price as llm_price  # noqa: E402  (Groq's listed price for these open weights)

OUT = Path(os.getenv("MOOT_EVAL_OUT") or ROOT / "eval")
STUDY = sys.argv[sys.argv.index("--study") + 1] if "--study" in sys.argv else "k1"  # "k2": the confirmation run, same harness
K = ROOT / "eval" / STUDY
Q = json.loads((K / "questions.json").read_text())
PINNED = (K / "QUESTIONS.sha256").read_text().split()[0] if (K / "QUESTIONS.sha256").exists() else None
CACHE = K / "cache.jsonl"
BACKEND = os.getenv("MOOT_K1_BACKEND", "ollama")  # "groq": the same open weights served by Groq (qwen/qwen3.8-27b)
MODEL = os.getenv("MOOT_K1_MODEL", "qwen/qwen3.8-27b" if BACKEND == "groq" else "qwen3.8:27b")
OLLAMA = os.getenv("OLLAMA_URL", "http://localhost:11434")
ENH = ROOT / "data" / "github" / ".repos" / "kubernetes__enhancements"
COM = ROOT / "data" / "github" / ".repos" / "kubernetes__community"
REPOS = {"enhancements": ENH, "community": COM}
GRAPH = "gh_kubernetes_enhancements"
ARMS = ("moot_tools", "file_tools", "rag_bm25", "rag_history", "moot_direct")
TEMPLATES = (1, 2, 3, 4, 5, 6) if "--study" in sys.argv and sys.argv[sys.argv.index("--study") + 1] == "k2" else (1, 2, 3, 4)
MAX_STEPS = 6
RESULT_CHARS = 3000  # a tool result in the conversation; keeps a run inside the model's 16k context


def refuse_if_changed() -> None:
    body = {k: v for k, v in Q.items() if k != "sha256"}
    now = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    if now != Q["sha256"] or now != PINNED:
        sys.exit(f"K1 questions changed: {now[:16]} vs pinned {str(PINNED)[:16]}; refusing to score")


FORMATS = {1: '{"kep": "KEP-<number>", "date": "YYYY-MM-DD"}', 2: '{"leads": ["<github handle>", ...]}',
           3: '{"in_force": true or false, "retired_by": "KEP-<number>" or "withdrawn" or "deferred" or null}',
           4: '{"authors": [["<github handle>", true or false], ...]}', 5: '{"count": <integer>}', 6: '{"was_lead": true or false}'}


_names: dict[str, str] | None = None


def names() -> dict[str, str]:
    """display name -> GitHub handle, from sigs.yaml at quarterly revisions since 2018 and HEAD (raw git, never Moot's graph)."""
    global _names
    if _names is None:
        from moot.k1 import COM as C, git as kgit, head_rev, load_yaml, show
        from moot.connectors.teams import quarters
        tip, _names = head_rev(C), {}
        revs = {kgit(C, "rev-list", "-1", f"--before={q}", tip).strip() for q in quarters("2018-01-01", Q["today"])} | {tip}
        for rev in filter(None, revs):
            for s in load_yaml(show(C, f"{rev}:sigs.yaml")).get("sigs", []):
                for grp in (s.get("leadership") or {}).values():
                    for p in grp or []:
                        if isinstance(p, dict) and p.get("name") and p.get("github"):
                            _names[str(p["name"]).strip().lower()] = str(p["github"]).strip().lower()
    return _names


def person(x) -> str:
    """One normaliser for every arm: a GitHub handle, or a display name mapped to one; case and a leading @ ignored."""
    s = str(x).strip().lstrip("@").lower()
    return names().get(s, s)


def norm(t: int, a) -> object:
    if not isinstance(a, dict):
        return None
    try:
        if t == 1:
            return (str(a.get("kep", "")).upper().replace(" ", ""), str(a.get("date", ""))[:10])
        if t == 2:
            return tuple(sorted({person(x) for x in a.get("leads") or []}))
        if t == 3:
            rb = a.get("retired_by")
            return (bool(a.get("in_force")), (str(rb).upper().replace(" ", "") if rb and str(rb).upper().startswith("KEP") else (str(rb).lower() if rb else None)))
        if t == 4:
            return tuple(sorted((person(x[0]), bool(x[1])) for x in a.get("authors") or []))
        if t == 5:
            return int(a.get("count"))
        if t == 6:
            return bool(a.get("was_lead"))
    except Exception:
        return None


def right(q: dict, a) -> bool:
    return a is not None and norm(q["template"], a) == norm(q["template"], q["gold"])


# ---- the model

def parse(reply: str) -> dict:
    """The first JSON object in the reply (a model may write a sentence before it, or several objects after)."""
    dec = json.JSONDecoder()
    for i, ch in enumerate(reply or ""):
        if ch == "{":
            try:
                x, _ = dec.raw_decode(reply[i:])
                if isinstance(x, dict):
                    return x
            except json.JSONDecodeError:
                continue
    return {}


def chat(messages: list[dict]) -> tuple[str, int, int, float]:
    if BACKEND == "groq":
        return chat_groq(messages)
    body = dict(model=MODEL, stream=False, think=False, options=dict(temperature=0, seed=7, num_ctx=16384, num_predict=600),
                messages=messages)  # no JSON mode in this build; a reply is one short JSON object
    t0 = time.perf_counter()
    for attempt in range(8):
        try:
            r = json.loads(urllib.request.urlopen(urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(body).encode(),
                                                                        headers={"content-type": "application/json"}), timeout=1200).read())
            return r["message"]["content"], r.get("prompt_eval_count", 0), r.get("eval_count", 0), time.perf_counter() - t0
        except Exception:  # the MLX build answers a transient 500 under GPU pressure
            if attempt == 7:
                raise
            time.sleep(20)
    raise RuntimeError


def chat_groq(messages: list[dict]) -> tuple[str, int, int, float]:
    from moot import llm
    body = dict(model=MODEL, temperature=0, seed=7, max_tokens=600, messages=messages)
    for attempt in range(20):
        req = urllib.request.Request(llm.GROQ_URL, data=json.dumps(body).encode(), headers={
            "content-type": "application/json", "authorization": f"Bearer {llm._env_key('GROQ_API_KEY')}", "user-agent": "moot"})
        t0 = time.perf_counter()
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=120).read())
            u = r.get("usage") or {}
            return r["choices"][0]["message"].get("content") or "", u.get("prompt_tokens", 0), u.get("completion_tokens", 0), time.perf_counter() - t0
        except urllib.error.HTTPError as e:
            detail = e.read()
            if e.code != 429 or attempt == 19:
                raise RuntimeError(f"Groq {e.code}: {detail[:300]!r}") from e
            wait = float(e.headers.get("retry-after") or 10)
            print(f"  rate limited, waiting {wait:.0f} s: {detail[:140]!r}", flush=True)
            time.sleep(wait)
    raise RuntimeError


SYSTEM = """You answer questions about the Kubernetes project's enhancement proposals (KEPs) and its SIGs. Use the tools to find \
facts; never answer from memory. Each reply is one JSON object: either {"tool": "<name>", "args": {...}} to call a tool, or \
{"answer": <the answer in the requested format>} to finish. Reply with that one object only, no other text. At most %d tool \
calls.""" % MAX_STEPS


def agent(q: dict, tool_doc: str, run) -> dict:
    msgs = [dict(role="system", content=SYSTEM + "\nTools:\n" + tool_doc),
            dict(role="user", content=f"{q['question']}\nAnswer format: {FORMATS[q['template']]}")]
    tin = tout = calls = 0
    secs = 0.0
    for step in range(MAX_STEPS + 2):
        reply, i, o, s = chat(msgs)
        tin, tout, secs = tin + i, tout + o, secs + s
        x = parse(reply)
        ans, done = answer_of(q["template"], x)
        if done:
            return dict(answer=ans, tokens_in=tin, tokens_out=tout, seconds=round(secs, 1), calls=calls, transcript=msgs[1:] + [dict(role="assistant", content=reply)])
        if x.get("tool") and calls < MAX_STEPS:
            calls += 1
            try:
                res = run(str(x["tool"]), x.get("args") or {})
            except Exception as ex:
                res = f"error: {ex}"
            msgs += [dict(role="assistant", content=reply), dict(role="user", content=f"Result of {x['tool']}:\n{str(res)[:RESULT_CHARS]}")]
            continue
        msgs += [dict(role="assistant", content=reply or "{}"), dict(role="user", content='Reply now with {"answer": ...} in the requested format.')]
    return dict(answer=None, tokens_in=tin, tokens_out=tout, seconds=round(secs, 1), calls=calls, transcript=msgs[1:])


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
    handles = lambda xs: [dict(x, handle=x["id"].removeprefix("u_")) for x in xs]  # dev fix: answers ask for GitHub handles
    if name == "team_on":
        t = tools.decision_team(G, kid, day)
        return json.dumps(dict(t, leads=handles(t["leads"]), former=handles(t["former"])) if t else None, default=str)
    if name == "kep_authors":
        return json.dumps(handles(tools.decision_authors(G, kid, day)), default=str)
    if name == "sig_keps" and STUDY != "k1":
        sig = str(a.get("sig", "")).lower().replace(" ", "-")
        sig = sig if sig.startswith("sig-") else "sig-" + sig
        rows = [r for r in tools.ledger(G, day, 4) if r["verdict"] != "RETIRED" and r["id"] in in_team(sig)]
        return json.dumps(dict(sig=sig, as_of=day, in_force=len(rows), keps=[r["id"] for r in rows][:200]))
    return "unknown tool"


def in_team(sig: str) -> set:
    return {r[0] for r in G.ro_query("MATCH (:Team {id: $t})-[:RESPONSIBLE_FOR]->(d:Decision) RETURN d.id", {"t": f"team_{sig}"}).result_set}


MOOT_DOC = """- find_kep(query): KEPs whose title matches
- audit_kep(kep, date): the KEP as of a date: verdict (HOLDS, MOOT, RETIRED, NOT_YET...), what superseded or retired it and when, the team that answers for it and its leads then
- kep_history(kep, date): every verdict the KEP has had and the date each began, up to the date
- team_on(kep, date): the SIG that answers for the KEP and its chairs and tech leads on that date (with their GitHub handle), and former leads
- kep_authors(kep, date): the KEP's authors (with their GitHub handle) and which SIG each leads on that date"""
if STUDY != "k1":
    MOOT_DOC += "\n- sig_keps(sig, date): how many of a SIG's KEPs were in force on a date, and which"


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
    if name == "read_file":  # fairness fix (register, item 5): a line window, so a 200 KB sigs.yaml is readable past its first 6,000 characters
        text = git("cat-file", "-p", f"{rev}:{a.get('path', '')}")
        if not text:
            return "no such file"
        lines = text.splitlines()
        lo = max(int(a.get("start") or 1), 1)
        hi = min(lo - 1 + min(int(a.get("lines") or 200), 400), len(lines))
        return (f"[lines {lo}-{hi} of {len(lines)}]\n" + "\n".join(lines[lo - 1:hi]))[:6000]
    if name == "grep":
        pat, pre = str(a.get("pattern", "")), str(a.get("prefix", "keps/" if repo == ENH else "sigs.yaml"))
        files = [f for f in git("ls-tree", "-r", "--name-only", rev).splitlines() if f.startswith(pre) and (f.endswith("kep.yaml") or f == "sigs.yaml")]
        out = []
        ctx = min(int(a.get("context") or 0), 60)
        for f in files:
            body = git("cat-file", "-p", f"{rev}:{f}").splitlines()
            for i, line in enumerate(body):
                if re.search(pat, line, re.I):
                    out.append(f"{f}:{i + 1}: {line.strip()}")
                    out += [f"{f}:{j + 1}- {body[j].rstrip()}" for j in range(i + 1, min(i + 1 + ctx, len(body)))]
            if len(out) > 80 + ctx:
                break
        return "\n".join(out[:80 + ctx])[:6000] or "no match"
    if name == "git_log":  # fairness fix (register, 12:05 UTC): dates reach the whole history, not just the 40 newest commits
        when = [f"--before={a['before']}T23:59:59"] if a.get("before") else []
        when += [f"--after={a['after']}"] if a.get("after") else []
        n = str(min(int(a.get("n") or 40), 100))
        return git("log", "--format=%H %cs %s", "-n", n, *when, rev, "--", str(a.get("path", "")))[:6000] or "no commits"
    return "unknown tool"


FILE_DOC = """- list_files(repo, prefix): file paths under a prefix; repo is "enhancements" (kubernetes/enhancements) or "community" (kubernetes/community)
- read_file(repo, path, rev, start, lines): a file's text at a commit (rev defaults to the latest), lines start..start+lines (default 1 and 200, at most 400)
- grep(repo, pattern, prefix, rev, context): lines matching a regex in kep.yaml files under a prefix (enhancements) or in sigs.yaml (community), at a commit (rev defaults to the latest), each with up to `context` following lines (at most 60)
- git_log(repo, path, before, after, n): the commits that changed a path, newest first (hash, date, subject); before / after are YYYY-MM-DD and optional, n at most 100 (default 40). Pass a hash as rev to read_file or grep to see the file at that commit"""


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


def history_pool() -> list[dict]:
    """Post hoc (register, 12:05 UTC): each KEP's status history and each SIG's leadership at every sigs.yaml commit that changed it,
    one document per SIG per year. Cached outside the repo, rebuilt from the checkouts."""
    from moot.k1 import keps, load_yaml, show
    cache = ROOT / "data" / "github" / ".repos" / f"{STUDY}_history_pool.json"  # one pool per study: K2 covers four SIGs
    if cache.exists():
        return json.loads(cache.read_text())
    pool = []
    for n, k in keps().items():
        lines = [f"{d}: status {s}" for i, (d, s) in enumerate(k["hist"]) if s and (i == 0 or s != k["hist"][i - 1][1])]
        pool.append(dict(id=f"history:KEP-{n}", text=f"KEP-{n} {k['title']} (owning-sig: {k['sig']}, {k['path']}) status history:\n" + "\n".join(lines)))
    g = lambda *x: subprocess.run(["git", "-C", str(COM), *x], capture_output=True, text=True, errors="replace").stdout
    changes: dict[str, list[tuple[str, str]]] = {}  # sig -> [(day, leadership text)] on the mainline (first parent), oldest first
    for line in g("log", "--first-parent", "--reverse", "--format=%H %cs", _rev(COM), "--", "sigs.yaml").splitlines():
        sha, day = line.split()
        for s in load_yaml(show(COM, f"{sha}:sigs.yaml")).get("sigs", []):
            lead = s.get("leadership") or {}
            text = "; ".join(f"{role.replace('_', ' ')}: " + ", ".join(f"{p.get('github')} ({p.get('name')})" for p in lead.get(role) or [] if isinstance(p, dict))
                             for role in ("chairs", "tech_leads"))
            xs = changes.setdefault(s.get("dir"), [])
            if not xs or xs[-1][1] != text:
                xs.append((day, text))
    for sig, xs in sorted(changes.items()):  # one document per SIG per year: who led it on 1 January, then every change that year
        for year in range(int(xs[0][0][:4]), int(Q["today"][:4]) + 1):
            start = [t for d, t in xs if d < f"{year}-01-01"]
            body = ([f"on {year}-01-01: {start[-1]}"] if start else []) + [f"from {d}: {t}" for d, t in xs if d[:4] == str(year)]
            pool.append(dict(id=f"history:{sig}:{year}", text=f"{sig} leadership in {year}, from sigs.yaml history:\n" + "\n".join(body)))
    cache.write_text(json.dumps(pool))
    return pool


POOL = None
POOL_H = None


def rag(q: dict, history: bool = False) -> dict:
    global POOL, POOL_H
    POOL = POOL or rag_pool()
    if history:
        POOL_H = POOL_H or POOL + history_pool()
    pool = POOL_H if history else POOL
    tok = lambda s: re.findall(r"[a-z0-9]+", s.lower())
    bm = BM25Okapi([tok(p["text"]) for p in pool])
    sc = bm.get_scores(tok(q["question"]))
    top = [pool[i] for i in sorted(range(len(pool)), key=lambda i: -sc[i])[:5]]
    ctx = "\n\n".join(f"[{p['id']}]\n{p['text']}" for p in top)
    reply, i, o, s = chat([dict(role="system", content="Answer from the context only. Reply with one JSON object: {\"answer\": <the answer in the requested format>}."),
                           dict(role="user", content=f"{q['question']}\nAnswer format: {FORMATS[q['template']]}\n\nContext:\n{ctx}")])
    ans = answer_of(q["template"], parse(reply))[0]
    return dict(answer=ans, tokens_in=i, tokens_out=o, seconds=round(s, 1), calls=0)


# ---- deterministic reference

def direct(q: dict):
    t, kid = q["template"], q.get("kep")
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
    if t == 5:
        return dict(count=sum(1 for r in tools.ledger(G, q["date"], 4) if r["verdict"] != "RETIRED" and r["id"] in in_team(q["sig"])))
    if t == 6:
        team = tools.decision_team(G, kid, q["date"])
        return dict(was_lead=q["person"] in {x["id"].removeprefix("u_") for x in (team or {}).get("leads", [])})


# the file tools' first description, kept verbatim: the HEAD-only RAG's cache key and every v1 answer's key are built from it
FILE_DOC_V1 = """- list_files(repo, prefix): file paths under a prefix; repo is "enhancements" (kubernetes/enhancements) or "community" (kubernetes/community)
- read_file(repo, path, rev): a file's text at a commit (rev defaults to the latest)
- grep(repo, pattern, prefix): lines matching a regex in kep.yaml files under a prefix (enhancements) or in sigs.yaml (community)
- git_log(repo, path): the commits that changed a path, newest first (hash, date, subject)"""


HARNESS = "v2"  # v2 (register, fairness audit): every arm accepts a bare answer object; v1 answers are kept, not scored


def key_for(arm: str, q: dict, model: str, harness: str = HARNESS) -> str:
    if harness == "v1":
        doc = dict(moot_tools=MOOT_DOC, file_tools=FILE_DOC_V1, rag_bm25=FILE_DOC_V1, rag_history="rag over history v1")[arm]
        return hashlib.sha256(json.dumps([arm, model, q["id"], SYSTEM, doc]).encode()).hexdigest()[:20]
    doc = dict(moot_tools=MOOT_DOC, file_tools=FILE_DOC, rag_bm25=FILE_DOC_V1, rag_history="rag over history v1")[arm]
    return hashlib.sha256(json.dumps([arm, model, q["id"], SYSTEM, doc, harness]).encode()).hexdigest()[:20]


KEYS = {1: {"kep", "date"}, 2: {"leads"}, 3: {"in_force", "retired_by"}, 4: {"authors"}, 5: {"count"}, 6: {"was_lead"}}


def answer_of(t: int, x: dict):
    """The answer in a reply, the same rule for every arm: {"answer": ...}, or the bare answer object the format asks for."""
    if "answer" in x:
        return x["answer"], True
    if "tool" not in x and KEYS[t] & set(x):
        return x, True
    return None, False


LOCAL = "qwen3.8:27b"  # the registered model; K1's test split was moved to Groq and back (docs/studies.md, amendments)
OTHER = "qwen/qwen3.8-27b" if MODEL == LOCAL else LOCAL  # its answers on test are listed, never scored


def cached(arm: str, q: dict, fill: bool, cache: dict) -> dict | None:
    key = key_for(arm, q, MODEL)
    if key in cache:
        return cache[key]
    if not fill:
        return None
    try:
        r = (agent(q, MOOT_DOC, moot_run) if arm == "moot_tools" else agent(q, FILE_DOC, file_run) if arm == "file_tools"
             else rag(q, history=arm == "rag_history"))
    except Exception as ex:  # the model server failed on this question after retries: scored as no answer, and recorded
        r = dict(answer=None, tokens_in=0, tokens_out=0, seconds=0.0, calls=0, error=str(ex)[:200])
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
    arms = sys.argv[sys.argv.index("--arms") + 1].split(",") if "--arms" in sys.argv else ARMS
    cache = {}
    if CACHE.exists():
        cache = {r["key"]: r for r in (json.loads(l) for l in CACHE.read_text().splitlines() if l.strip())}
    rows = []
    for q in Q["questions"]:
        r = dict(id=q["id"], template=q["template"], split=q["split"])
        r["moot_direct"] = right(q, direct(q))
        for arm in ("moot_tools", "file_tools", "rag_bm25", "rag_history"):
            c = cached(arm, q, fill and (only is None or q["split"] == only) and arm in arms, cache)
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
            per = {t: f"{sum(r[arm] for r in got if r['template'] == t)}/{sum(1 for r in got if r['template'] == t)}" for t in TEMPLATES}
            costs = [r[arm + "_cost"] for r in got if arm + "_cost" in r]
            res[split][arm] = dict(right=k, n=len(got), of=len(rs), ci=wilson(k, len(got)), per_template=per,
                                   tokens=sum(c["tokens_in"] + c["tokens_out"] for c in costs),
                                   seconds_median=sorted(c["seconds"] for c in costs)[len(costs) // 2] if costs else None,
                                   calls=sum(c["calls"] for c in costs),
                                   usd=round(sum(llm_price("qwen/qwen3.8-27b", c["tokens_in"], c["tokens_out"]) for c in costs), 4))
        res[split]["paired"] = {}
        for other in ("file_tools", "rag_bm25", "rag_history"):  # exact McNemar, the graph agent against each baseline, questions both answered
            both = [r for r in rs if r["moot_tools"] is not None and r[other] is not None]
            b_, c_ = sum(1 for r in both if r["moot_tools"] and not r[other]), sum(1 for r in both if r[other] and not r["moot_tools"])
            res[split]["paired"][other] = dict(n=len(both), only_moot=b_, only_other=c_, p=round(mcnemar_exact(b_, c_), 3))
    (OUT / f"results_{STUDY}.json").write_text(json.dumps(dict(model=MODEL, questions_sha256=Q["sha256"], results=res, rows=rows), indent=1) + "\n")
    names = dict(moot_tools="**agent with Moot's graph tools**", file_tools="agent with file and git tools over the same checkouts",
                 rag_bm25="BM25 RAG over the checkouts at HEAD", rag_history="BM25 RAG over the checkouts and their history (post hoc, see register)", moot_direct="Moot, one fixed graph query per template, no model (shared-source reference)")
    L = [f"# {STUDY.upper()}: questions about Kubernetes as an organisation (study {STUDY.upper()})", "",
         f"{len(Q['questions'])} templated questions about SIG Auth and SIG Node KEPs; gold from the raw git history of kubernetes/enhancements and "
         f"kubernetes/community (`moot/k1.py`), hashed before any arm ran (`{Q['sha256'][:16]}…`). Same model ({MODEL}, temperature 0) for every "
         "model arm" + (f"; **deviation:** the register named {LOCAL} through Ollama; it ran at about ten minutes a question, so test and dev were "
                        f"re-run on the same open weights served by Groq, amended before any Groq answer was read (docs/studies.md; the local answers "
                        f"are listed below)." if MODEL != LOCAL else ".") + " **Shared-source caveat:** Moot's graph is built from the same files, so its fixed-query row is close to the gold by construction; "
         "the contest is between agents with the same model and different tools. Templates: (1) which KEP replaced it and when, (2) who led its SIG "
         "on a date, (3) was it in force on a date and what retired it, (4) its authors and whether each leads a SIG today.", ""]
    for split in ("test", "dev"):
        L += [f"## {split.title()} split", "", "| arm | exact match (95% CI) | " + " | ".join(f"t{t}" for t in TEMPLATES) + " | tokens | $ at Groq's price | median s per question | tool calls |",
              "|" + "---|" * (len(TEMPLATES) + 6)]
        for arm in ARMS:
            s = res[split][arm]
            if not s["n"]:
                continue
            L.append(f"| {names[arm]} | {s['right']}/{s['n']} ({s['ci'][0]:.2f}–{s['ci'][1]:.2f}) | " + " | ".join(s["per_template"][t] for t in TEMPLATES)
                     + f" | {s['tokens']:,} | {s['usd']:.3f} | {s['seconds_median'] if s['seconds_median'] is not None else '–'} | {s['calls']} |")
        L.append("")
        for other, pr in res[split]["paired"].items():
            if pr["n"]:
                L.append(f"- graph agent vs {names[other].strip('*')}: on {pr['n']} questions both answered, only the graph agent right on "
                         f"{pr['only_moot']}, only the other on {pr['only_other']}; exact McNemar p = {pr['p']}")
        L.append("")
    if OTHER:
        local = [(arm, q, cache[key_for(arm, q, OTHER, "v1")]) for q in Q["questions"] for arm in ("moot_tools", "file_tools", "rag_bm25")
                 if q["split"] == "test" and key_for(arm, q, OTHER, "v1") in cache]
        if local:
            L += [f"## The {len(local)} test answers produced on {OTHER} (not in the table above)", "",
                  "The register's amendments explain why these exist; they are listed so nothing is dropped.", "",
                  f"| question | arm | {OTHER} | {MODEL} on the same question |", "|---|---|---|---|"]
            for arm, q, c in local:
                g = cache.get(key_for(arm, q, MODEL))
                mark = lambda x: "no answer" if x is None or x.get("answer") is None else ("right" if right(q, x["answer"]) else "wrong")
                L.append(f"| {q['id']} (t{q['template']}) | {arm} | {mark(c)} | {mark(g) if g else 'not yet run'} |")
            n_l = sum(1 for _, q, c in local if c.get("answer") is not None and right(q, c["answer"]))
            n_g = sum(1 for arm, q, _ in local if (g := cache.get(key_for(arm, q, MODEL))) and g.get("answer") is not None and right(q, g["answer"]))
            L += ["", f"On these {len(local)}: {OTHER} {n_l} right, {MODEL} {n_g} right.", ""]
    (OUT / f"results_{STUDY}.md").write_text("\n".join(L) + "\n")
    t = res["test"]
    print("test: " + ", ".join(f"{a} {t[a]['right']}/{t[a]['n']}" for a in ARMS))


if __name__ == "__main__":
    main()
