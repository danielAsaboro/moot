"""Head-to-head: Moot's graph verdicts against a plain retrieval company brain, plus ablations (study S3, docs/studies.md).

The question set and labels are frozen in eval/baseline/questions.json (eval/baseline_questions.py, from truth.json only)
before any arm ran. For each decision on three dates: does it still hold, which documents decided that, since when?

Arms without a model (deterministic, re-run by `moot verify --rerun`):
  moot              the audit at depth 4 as of the date; why = the contradicting evidence; since = tools.verdict_history
  moot_depth1       the same at depth 1: only the reasons the ADR states
  moot_no_asof      the same with dates ignored (every edge counts, whatever its date)
  no_falkordb       the graph removed, rules kept: the ADR's stated reasons, BM25 top-3 documents for each, a later
                    document with a change cue counts as a contradiction on its date (the change cues of eval_scale)
  trust_adr         a doc-chat brain that finds the ADR and stops: HOLDS once decided

Arms with a model (the same local model, prompt and decoding for all three; answers cached in eval/baseline/llm_cache.jsonl):
  rag_bm25          the ADR + BM25 top-5 over every other document (PRs, tickets, chat, docs, the other ADRs)
  rag_premises      FalkorDB removed, model kept: the ADR, its stated reasons, and BM25 top-3 per reason
  moot_rows         Moot's audit rows (the graph's answer) as the context, so the model only reads the path

  python3 eval/eval_baseline.py           score every arm (model arms from the cache) -> eval/results_baseline.{md,json}
  python3 eval/eval_baseline.py --llm     first fill the model cache for missing answers (needs Ollama), resumable
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

from rank_bm25 import BM25Okapi

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from moot import tools  # noqa: E402
from moot.graph import DATA, connect, seed  # noqa: E402
from eval_scale import CUES  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.getenv("MOOT_EVAL_OUT") or ROOT / "eval")
BASE = ROOT / "eval" / "baseline"
CACHE = BASE / "llm_cache.jsonl"
MODEL = os.getenv("MOOT_BASELINE_MODEL", "qwen3.8:27b")
OLLAMA = os.getenv("OLLAMA_URL", "http://localhost:11434")
VERDICTS = ("HOLDS", "MOOT", "DISPUTED", "UNDOCUMENTED", "RETIRED", "NOT_YET")
DEAD = ("MOOT", "DISPUTED")
DETERMINISTIC = ("moot", "moot_depth1", "moot_no_asof", "no_falkordb", "trust_adr")
MODEL_ARMS = ("rag_bm25", "rag_premises", "moot_rows")
NO_DATE = "9999-12-31"

truth = json.loads((DATA / "truth.json").read_text())
QS = json.loads((BASE / "questions.json").read_text())["questions"]

SYSTEM = """You audit a company's standing decisions using only the context provided. Answer as of the date in the question: \
anything dated after that date had not happened yet.
Verdicts:
HOLDS: every reason the decision rests on still holds.
MOOT: a reason it rests on, directly or through a reason that reason depends on, was contradicted and not re-affirmed since.
DISPUTED: a reason was contradicted and later re-affirmed.
UNDOCUMENTED: the decision records no reason.
RETIRED: a later decision superseded it.
NOT_YET: it had not been decided by that date.
Reply with one JSON object and nothing else:
{"verdict": "<one verdict>", "evidence": ["<ids of the documents that decided it>"], "since": "<YYYY-MM-DD the current verdict began, or null>"}"""


def tok(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def pool() -> list[dict]:
    """Every document a retrieval brain would index: the 208 non-ADR documents and the 30 ADRs."""
    docs = [dict(id=e["id"], kind=e["kind"], date=e["date"], title=e["title"], text=e["text"]) for e in truth["evidence"]]
    for d in truth["decisions"]:
        docs.append(dict(id=f"src:{d['id']}", kind="adr", date=d["decided_on"], title=d["title"],
                         text=(DATA / "corpus" / d["source"]).read_text()))
    return docs


DOCS = pool()
BM = BM25Okapi([tok(f"{x['title']} {x['text']}") for x in DOCS])
DEC = {d["id"]: d for d in truth["decisions"]}
PREM = {p["id"]: p for p in truth["premises"]}


def top(query: str, k: int, exclude: set[str] = frozenset()) -> list[dict]:
    s = BM.get_scores(tok(query))
    return [DOCS[i] for i in sorted(range(len(DOCS)), key=lambda i: -s[i]) if DOCS[i]["id"] not in exclude][:k]


def fmt(x: dict) -> str:
    return f"[{x['id']}] ({x['kind']}, {x['date']}) {x['title']}\n{x['text'].strip()}"


# ---- deterministic arms

def moot_arm(g, q: dict, depth: int = 4, dated: bool = True) -> dict:
    at = q["as_of"] if dated else NO_DATE
    a = tools.audit_decision(g, q["decision_id"], at, depth)
    why = sorted({e["id"] for p in a["premises"] if p["state"] in ("expired", "disputed") for e in p["evidence"] if e["rel"] == "CONTRADICTS"})
    h = tools.verdict_history(g, q["decision_id"], at, depth)
    return dict(verdict=a["verdict"], evidence=why, since=h["since"])


def no_falkordb(q: dict) -> dict:
    d = DEC[q["decision_id"]]
    if d["decided_on"] > q["as_of"]:
        return dict(verdict="NOT_YET", evidence=[], since=None)
    if not d["premises"]:
        return dict(verdict="UNDOCUMENTED", evidence=[], since=None)
    hits = []
    for pid in d["premises"]:  # the reasons the ADR states; the reasons below them are graph edges, gone with the graph
        for x in top(PREM[pid]["text"], 3, {f"src:{d['id']}"}):
            if d["decided_on"] < x["date"] <= q["as_of"] and CUES.search(f"{x['title']} {x['text']}"):
                hits.append(x)
    if not hits:
        return dict(verdict="HOLDS", evidence=[], since=None)
    return dict(verdict="MOOT", evidence=sorted({x["id"] for x in hits}), since=min(x["date"] for x in hits))


def trust_adr(q: dict) -> dict:
    return dict(verdict="NOT_YET" if DEC[q["decision_id"]]["decided_on"] > q["as_of"] else "HOLDS", evidence=[], since=None)


# ---- model arms

def context(g, arm: str, q: dict) -> str:
    d = DEC[q["decision_id"]]
    adr = next(x for x in DOCS if x["id"] == f"src:{d['id']}")
    if arm == "rag_bm25":
        return "\n\n".join(fmt(x) for x in [adr, *top(q["question"], 5, {adr["id"]})])
    if arm == "rag_premises":
        seen, docs = {adr["id"]}, [adr]
        for pid in d["premises"]:
            for x in top(PREM[pid]["text"], 3, seen):
                seen.add(x["id"]); docs.append(x)
        reasons = "\n".join(f"- {PREM[p]['text']}" for p in d["premises"]) or "- (none recorded)"
        return f"Reasons the ADR states:\n{reasons}\n\n" + "\n\n".join(fmt(x) for x in docs)
    a = tools.audit_decision(g, d["id"], q["as_of"], 4)
    rows = dict(decision={k: a["decision"].get(k) for k in ("id", "title", "decided_on")}, verdict_rows_as_of=a["as_of"],
                not_yet=a["verdict"] == "NOT_YET", superseded_by=a.get("superseded_by"),
                premises=[dict(text=p["text"], hops=p["hops"], path=[n["title"] for n in p["path"]], state=p["state"],
                               evidence=[{k: e.get(k) for k in ("id", "rel", "at", "title", "quote")} for e in p["evidence"]])
                          for p in a["premises"]])
    return "Rows returned by the graph database (Moot's audit):\n" + json.dumps(rows, indent=1, default=str)


def prompt(g, arm: str, q: dict) -> str:
    return f"Context:\n{context(g, arm, q)}\n\nQuestion: {q['question']}"


def key(arm: str, p: str) -> str:
    return hashlib.sha256(json.dumps([MODEL, SYSTEM, arm, p]).encode()).hexdigest()[:24]


def load_cache() -> dict[str, dict]:
    if not CACHE.exists():
        return {}
    return {r["key"]: r for r in map(json.loads, CACHE.read_text().splitlines()) if r.get("reply") is not None}


def call(p: str) -> str:
    body = dict(model=MODEL, stream=False, think=False, options=dict(temperature=0, seed=7, num_ctx=16384),
                messages=[dict(role="system", content=SYSTEM), dict(role="user", content=p)])
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(body).encode(), headers={"content-type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=900).read())["message"]["content"]


def parse(reply: str) -> dict:
    m = re.search(r"\{.*\}", reply, re.S)
    try:
        x = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        x = {}
    v = str(x.get("verdict", "")).strip().upper().replace(" ", "_")
    since = x.get("since")
    since = since if isinstance(since, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", since) else None
    ev = [str(e).strip("[] ") for e in x.get("evidence") or [] if isinstance(e, (str, int))]
    return dict(verdict=v if v in VERDICTS else "UNPARSED", evidence=ev, since=since)


def fill(g) -> None:
    cache = load_cache()
    todo = [(arm, q) for arm in ("moot_rows", "rag_bm25", "rag_premises") for q in QS if key(arm, prompt(g, arm, q)) not in cache]
    print(f"{len(todo)} model answers to fill", flush=True)
    with CACHE.open("a") as f:
        for i, (arm, q) in enumerate(todo, 1):
            p = prompt(g, arm, q)
            reply = call(p)
            f.write(json.dumps(dict(key=key(arm, p), arm=arm, qid=q["id"], model=MODEL, reply=reply)) + "\n")
            f.flush()
            print(f"{i}/{len(todo)} {arm} {q['id']}: {parse(reply)['verdict']}", flush=True)


# ---- scoring

def score(answers: dict[str, dict]) -> dict:
    n = len(QS)
    dead = [q for q in QS if q["label"]["verdict"] in DEAD]
    dated = [q for q in QS if q["label"]["since"]]
    holds = [q for q in QS if q["label"]["verdict"] == "HOLDS"]
    a = lambda q: answers.get(q["id"])
    got = [q for q in QS if a(q)]
    return dict(
        answered=len(got), n=n,
        verdict=sum(1 for q in got if a(q)["verdict"] == q["label"]["verdict"]),
        dead_n=len(dead), dead_called_holds=sorted(q["id"] for q in dead if a(q) and a(q)["verdict"] == "HOLDS"),
        why=sum(1 for q in dead if a(q) and set(a(q)["evidence"]) & set(q["label"]["invalidating"])),
        since_n=len(dated), since=sum(1 for q in dated if a(q) and a(q)["since"] == q["label"]["since"]),
        holds_n=len(holds), false_alarms=sorted(q["id"] for q in holds if a(q) and a(q)["verdict"] in ("MOOT", "DISPUTED", "RETIRED")),
        by_date={t: sum(1 for q in got if q["as_of"] == t and a(q)["verdict"] == q["label"]["verdict"]) for t in sorted({q["as_of"] for q in QS})},
        unparsed=sum(1 for q in got if a(q)["verdict"] == "UNPARSED"))


LABEL = {"moot": "**Moot** (graph verdict, depth 4)", "moot_rows": "Moot rows + model (the graph's path, narrated)",
         "rag_bm25": "RAG: BM25 top-5 + model", "rag_premises": "RAG over stated reasons + model (FalkorDB removed)",
         "moot_depth1": "ablation: depth 1", "moot_no_asof": "ablation: no as_of (dates ignored)",
         "no_falkordb": "ablation: FalkorDB removed, rules kept", "trust_adr": "trust the ADR"}


def main(llm: bool = False) -> None:
    db = connect()
    g = db.select_graph("moot_eval_baseline")
    seed(g, None, fresh=True)
    if llm:
        fill(g)
    answers = {"moot": {q["id"]: moot_arm(g, q) for q in QS},
               "moot_depth1": {q["id"]: moot_arm(g, q, depth=1) for q in QS},
               "moot_no_asof": {q["id"]: moot_arm(g, q, dated=False) for q in QS},
               "no_falkordb": {q["id"]: no_falkordb(q) for q in QS},
               "trust_adr": {q["id"]: trust_adr(q) for q in QS}}
    cache = load_cache()
    for arm in MODEL_ARMS:
        answers[arm] = {}
        for q in QS:
            r = cache.get(key(arm, prompt(g, arm, q)))
            if r:
                answers[arm][q["id"]] = parse(r["reply"])
    g.delete()
    s = {arm: score(x) for arm, x in answers.items()}
    write(s, answers)


def write(s: dict, answers: dict) -> None:
    x0 = s["moot"]
    dates = sorted({q["as_of"] for q in QS})
    out = ["# Head-to-head: graph verdicts against a retrieval company brain", "",
           f"Study S3 ([docs/studies.md](../docs/studies.md)), registered before it ran. {len(QS)} questions: each of Larkspur's "
           f"{len(DEC)} decisions on {len(dates)} dates ({', '.join(dates)}), asked *does it still hold, which documents show it, since when?* "
           "Labels were frozen from `truth.json` alone (`eval/baseline/questions.json`, `eval/baseline_questions.py`) with a verdict rule "
           "written independently of `moot/verdict.py`. Model arms use the same local model, prompt and decoding "
           f"(`{MODEL}`, temperature 0, seed 7); only the context differs.", "",
           f"| arm | verdicts right (of {x0['n']}) | dead decisions called HOLDS (of {x0['dead_n']}) | cited a document that killed it (of {x0['dead_n']}) | "
           f"\"since when\" exact (of {x0['since_n']}) | false alarms on HOLDS (of {x0['holds_n']}) |", "|---|---|---|---|---|---|"]
    for arm in ("moot", "moot_rows", "rag_bm25", "rag_premises", "moot_depth1", "moot_no_asof", "no_falkordb", "trust_adr"):
        r = s[arm]
        if not r["answered"]:
            out.append(f"| {LABEL[arm]} | not run | | | | |")
            continue
        part = "" if r["answered"] == r["n"] else f" ({r['answered']} answered)"
        b = "**" if arm == "moot" else ""
        out.append(f"| {LABEL[arm]}{part} | {b}{r['verdict']}{b} | {b}{len(r['dead_called_holds'])}{b} | {b}{r['why']}{b} | {b}{r['since']}{b} | {len(r['false_alarms'])} |")
    out += ["", "Verdicts right, by date:", "", "| arm | " + " | ".join(dates) + " |", "|---|" + "---|" * len(dates)]
    n_by = {t: sum(1 for q in QS if q["as_of"] == t) for t in dates}
    for arm, r in s.items():
        if r["answered"]:
            out.append(f"| {LABEL[arm]} | " + " | ".join(f"{r['by_date'][t]}/{n_by[t]}" for t in dates) + " |")
    out += ["", "## Threats to validity, worst first", "",
            "1. **Common-mode answer key.** The Moot arms read a graph built from the same spec as the labels, so their scores measure what the "
            "path rules and dated edges do *given* correct edges, an upper bound for Moot. The retrieval arms read the raw documents. The question "
            "this answers is what a retrieval brain loses against a correctly built graph, not whether extraction builds one.",
            f"2. **Small and synthetic.** {len(QS)} questions about {len(DEC)} decisions in an invented company, and the dates share decisions, so "
            "the questions are not independent.",
            "3. **One local model, one run.** The model arms ran once on a local open-weights model; answers are cached in "
            "`eval/baseline/llm_cache.jsonl` so the scores re-derive exactly, but a stronger model would likely do better on both sides of the comparison.",
            "4. **The retrieval arms get the rule definitions in the prompt**, which a real doc-chat brain would not have. That favours them."]
    (OUT / "results_baseline.md").write_text("\n".join(out) + "\n")
    (OUT / "results_baseline.json").write_text(json.dumps(dict(model=MODEL, n=len(QS), dates=dates, arms=s,
                                                              answers={a: answers[a] for a in DETERMINISTIC}), indent=1, sort_keys=True) + "\n")
    print("\n".join(out[:16]))


if __name__ == "__main__":
    main(llm="--llm" in sys.argv)
