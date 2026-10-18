"""Study H1: does this real decision still hold? Every arm sees only what existed on T0; the repositories grade it later.

Gold and the frozen dev/test split: eval/heldout/gold.json (moot/heldout/gold.py), hashed before any arm ran. This script
refuses to score if the gold's hash differs from eval/heldout/GOLD.sha256. Inputs: data/heldout/inputs.json
(moot/heldout/inputs.py): each ADR as it stood on T0 without its Status section, the repository's other ADRs on T0, and
the dated tool evidence up to T0 (commit history gaps, licence announcements, OSV advisories published by T0).

Arms (each answers HOLDS or DEAD for every unit):
  moot               the agent gate in a FalkorDB graph built like the backtest's, asked as of T0: DENY = DEAD
  moot_no_falkordb   the same verdict rules with the graph removed: BM25 picks the 3 evidence documents most like the ADR,
                     and a decision is DEAD if a retrieved premise's latest event is a contradiction
  majority           the dev split's majority class for everything
  age                DEAD when the decision is 3 years old or more on T0 (the backtest's age rule)
  trust_adr          the ADR's status on T0, which says in force for every unit (that is how a unit qualifies)
  rag_bm25           a model reads the ADR plus the BM25 top 5 of the repository's other ADRs and the tool evidence
                     (local qwen3.8:27b through Ollama, the S3 baseline's model and decoding)
  agent_tools        a model with tools (read the ADR, search and read the repository's ADRs, GitHub activity, licence
                     history, OSV advisories, all cut at T0) decides itself (Groq openai/gpt-oss-20b); tokens, dollars
                     and latency are recorded

Model replies are cached (eval/heldout/llm_cache.jsonl, eval/heldout/agent_cache.jsonl), so a re-run without --llm re-scores
offline. Prompts were fixed on the dev split before the test split ran (docs/studies.md H1).

  python3 eval/eval_heldout.py            score every arm from the caches -> eval/results_heldout.{md,json}
  python3 eval/eval_heldout.py --llm      first fill the model caches for missing units (Ollama for rag_bm25, Groq for the agent)
  python3 eval/eval_heldout.py --llm --split dev      only the dev split (prompt development)
  python3 eval/eval_heldout.py --llm --arms agent_tools   fill one model arm only (they can run side by side)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from rank_bm25 import BM25Okapi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from moot import llm  # noqa: E402
from moot.backtest.run import build  # noqa: E402
from moot.graph import connect, seed  # noqa: E402
from moot.heldout.evidence import merged  # noqa: E402
from moot.heldout.gold import digest  # noqa: E402
from moot.stats import mcnemar_exact, wilson  # noqa: E402
from moot.tools import check_action  # noqa: E402
from moot.verdict import premise_state  # noqa: E402

OUT = Path(os.getenv("MOOT_EVAL_OUT") or ROOT / "eval")
H = ROOT / "eval" / "heldout"
GOLD = json.loads(Path(os.getenv("MOOT_HELDOUT_GOLD") or H / "gold.json").read_text())
PINNED = (H / "GOLD.sha256").read_text().split()[0]
INPUTS = json.loads((ROOT / "data" / "heldout" / "inputs.json").read_text())
LLM_CACHE, AGENT_CACHE = H / "llm_cache.jsonl", H / "agent_cache.jsonl"
RAG_MODEL = os.getenv("MOOT_HELDOUT_RAG_MODEL", "qwen3.8:27b")
AGENT_MODEL = os.getenv("MOOT_HELDOUT_AGENT_MODEL", "openai/gpt-oss-20b")
OLLAMA = os.getenv("OLLAMA_URL", "http://localhost:11434")
ARMS = ("moot", "moot_no_falkordb", "majority", "age", "trust_adr", "rag_bm25", "agent_tools")
MODEL_ARMS = ("rag_bm25", "agent_tools")
POSTHOC = ("moot_advisory",)  # added after the first test numbers were seen; never replaces a frozen row
T0 = GOLD["t0"]


def refuse_if_gold_changed() -> None:
    now = digest(GOLD)
    if now != GOLD["sha256"] or now != PINNED:
        sys.exit(f"gold changed: sha256 {now[:16]} but pinned {PINNED[:16]} (eval/heldout/GOLD.sha256); refusing to score")


def tok(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


UNITS = {u["id"]: dict(u, others=[dict(path=q, **v) for q, v in sorted(INPUTS["repos"][u["repo"]]["adrs"].items()) if q != u["path_t0"]])
         for u in INPUTS["units"]}
EVIDENCE = [d for docs in INPUTS["evidence"].values() for d in docs]


def years_before(day: str, n: int) -> str:
    return f"{int(day[:4]) - n:04d}{day[4:]}"


# ---- arms without a model

def arm_moot(advisory: bool = False) -> dict[str, dict]:
    """advisory=True is the post-hoc row: licence checks count as DISPUTED, never expired (the rule moot/connectors/github.py
    has applied to ingested repositories since ac86bea, which predates this study's gold), justified on the dev split only."""
    ev = merged()
    decisions = [dict(id=u["id"], title=u["title"], born=u["born"], url=g["url"], repo=u["repo"], tools=[t for t in u["tools"] if t in ev])
                 for g in GOLD["units"] for u in [UNITS[g["id"]]]]
    g = connect().select_graph(f"moot_eval_heldout_{os.getpid()}")
    path = ROOT / "data" / "heldout" / ("graph_advisory.json" if advisory else "graph.json")
    payload = build(decisions, {t: ev[t] for t in {t for d in decisions for t in d["tools"]}})
    if advisory:
        for n in payload["nodes"]:
            if n["label"] == "Premise" and n["props"].get("check") == "open_source":
                n["props"]["advisory"] = True
    path.write_text(json.dumps(payload, indent=1))
    seed(g, path, fresh=True)
    try:
        out = {}
        for d in decisions:
            a = check_action(g, d["id"], T0)
            out[d["id"]] = dict(pred="DEAD" if a["gate"] == "DENY" else "HOLDS", gate=a["gate"],
                                why=next((r["text"] for r in a["reasons"] if r["code"] == "premise_expired"), a["reasons"][0]["text"] if a["reasons"] else ""))
        return out
    finally:
        g.delete()


def arm_no_falkordb() -> dict[str, dict]:
    bm = BM25Okapi([tok(d["title"]) for d in EVIDENCE])
    out = {}
    for i, u in UNITS.items():
        scores = bm.get_scores(tok(f"{u['title']} {u['adr'][:1500]}"))
        top = [EVIDENCE[j] for j in sorted(range(len(EVIDENCE)), key=lambda j: -scores[j])[:3] if scores[j] > 0]
        by_premise: dict[tuple, list] = {}
        for d in top:
            by_premise.setdefault((d["tool"], d["check"]), []).append(dict(rel=d["rel"], at=d["at"]))
        dead = [k for k, evs in by_premise.items() if premise_state(evs) == "expired"]
        out[i] = dict(pred="DEAD" if dead else "HOLDS", why=f"retrieved {', '.join(d['id'] for d in top)}" if top else "nothing retrieved")
    return out


def arm_majority() -> dict[str, dict]:
    dev = [g["gold"] for g in GOLD["units"] if g["split"] == "dev"]
    m = max(("HOLDS", "DEAD"), key=dev.count)
    return {i: dict(pred=m, why=f"the dev split's majority class ({dev.count(m)} of {len(dev)})") for i in UNITS}


def arm_age() -> dict[str, dict]:
    cut = years_before(T0, 3)
    return {i: dict(pred="DEAD" if u["born"] <= cut else "HOLDS", why=f"decided {u['born']}") for i, u in UNITS.items()}


def arm_trust() -> dict[str, dict]:
    return {i: dict(pred="HOLDS", why="its status on T0 says it is in force") for i in UNITS}


# ---- model arms

SYSTEM = f"""You audit a team's standing architecture decisions. Today is {T0}: nothing after that date has happened yet.
Decide whether the decision below still holds today, from the context only.
HOLDS: the team should keep following it; nothing in the context shows its reasons have gone away.
DEAD: something in the context shows the decision has been, or should be, abandoned: a reason it rests on is no longer
true (the tool it picked is unmaintained, changed its licence, was replaced in a later decision), or a later decision undoes it.
Reply with one JSON object and nothing else: {{"verdict": "HOLDS" or "DEAD", "why": "<one sentence>", "evidence": ["<ids or paths you relied on>"]}}"""


def _cache(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {r["key"]: r for r in (json.loads(l) for l in path.read_text().splitlines() if l.strip())}


def _parse(reply: str) -> dict:
    m = re.search(r"\{.*\}", reply or "", re.S)
    try:
        x = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        x = {}
    v = str(x.get("verdict", "")).upper()
    return dict(pred=v if v in ("HOLDS", "DEAD") else "HOLDS", why=str(x.get("why", ""))[:300], parsed=v in ("HOLDS", "DEAD"))


def rag_prompt(u: dict) -> str:
    pool = [dict(id=o["path"], text=f"{o['title']}\n{o['text'][:1500]}") for o in u["others"]] + \
           [dict(id=d["id"], text=f"{d['at']}: {d['title']}") for d in EVIDENCE]
    bm = BM25Okapi([tok(p["text"]) for p in pool])
    scores = bm.get_scores(tok(f"{u['title']} {u['adr'][:1500]}"))
    top = [pool[j] for j in sorted(range(len(pool)), key=lambda j: -scores[j])[:5]]
    ctx = "\n\n".join(f"[{p['id']}]\n{p['text']}" for p in top)
    return f"Decision ({u['repo']}, decided {u['born']}): {u['title']}\n\n{u['adr'][:4000]}\n\nRetrieved context:\n{ctx}"


def ollama(system: str, user: str) -> tuple[str, float]:
    body = dict(model=RAG_MODEL, stream=False, think=False, options=dict(temperature=0, seed=7, num_ctx=16384),
                messages=[dict(role="system", content=system), dict(role="user", content=user)])
    t0 = time.perf_counter()
    for attempt in range(4):
        try:
            req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(body).encode(), headers={"content-type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=1200).read())["message"]["content"], time.perf_counter() - t0
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == 3:
                raise
            time.sleep(10)
    raise RuntimeError("unreachable")


def arm_rag(fill: bool, ids: list[str]) -> dict[str, dict]:
    cache, out = _cache(LLM_CACHE), {}
    for i in ids:
        user = rag_prompt(UNITS[i])
        key = hashlib.sha256(json.dumps([RAG_MODEL, SYSTEM, user]).encode()).hexdigest()[:24]
        if key not in cache and fill:
            reply, secs = ollama(SYSTEM, user)
            row = dict(key=key, id=i, model=RAG_MODEL, reply=reply, seconds=round(secs, 1))
            with LLM_CACHE.open("a") as f:
                f.write(json.dumps(row) + "\n")
            cache[key] = row
            print(f"rag {i}: {_parse(reply)['pred']}", flush=True)
        if key in cache:
            out[i] = dict(_parse(cache[key]["reply"]), seconds=cache[key]["seconds"])
    return out


AGENT_SYSTEM = SYSTEM.replace("from the context only.", "using the tools; they only return what existed on that date.").split("Reply with")[0] + \
    "Call tools as needed (at most 6 calls), then call final_answer once with your verdict."
AGENT_TOOLS = [
    dict(name="read_decision", description="The decision's ADR text as it stood today (its status line removed).", parameters=dict(type="object", properties={})),
    dict(name="search_repo_adrs", description="Search the repository's other ADRs as they stood today; returns paths, titles and a snippet.",
         parameters=dict(type="object", properties=dict(query=dict(type="string")), required=["query"])),
    dict(name="read_repo_adr", description="Read one of the repository's other ADRs by path.",
         parameters=dict(type="object", properties=dict(path=dict(type="string")), required=["path"])),
    dict(name="github_activity", description="The tool's own GitHub repository: first commit and every gap of more than a year without commits, up to today.",
         parameters=dict(type="object", properties=dict(tool=dict(type="string")), required=["tool"])),
    dict(name="licence_history", description="The tool vendor's dated licence announcements up to today.",
         parameters=dict(type="object", properties=dict(tool=dict(type="string")), required=["tool"])),
    dict(name="osv_advisories", description="OSV.dev security advisories for the tool's package published up to today.",
         parameters=dict(type="object", properties=dict(tool=dict(type="string")), required=["tool"])),
    dict(name="final_answer", description="Your verdict on the decision. Call it once, last.",
         parameters=dict(type="object", properties=dict(verdict=dict(type="string", enum=["HOLDS", "DEAD"]), why=dict(type="string"),
                                                        evidence=dict(type="array", items=dict(type="string"))), required=["verdict", "why"])),
]


def run_tool(u: dict, name: str, args: dict) -> str:
    tid = str(args.get("tool", "")).lower()
    tools = INPUTS["tools"]
    if name in ("github_activity", "licence_history", "osv_advisories"):
        tid = next((t for t in u["tools"] if t == tid or tools[t]["name"].lower() == tid), u["tools"][0] if u["tools"] else tid)
    if name == "read_decision":
        return f"{u['title']} (decided {u['born']})\n\n{u['adr'][:5000]}"
    if name == "search_repo_adrs":
        docs = u["others"]
        if not docs:
            return "no other ADRs"
        bm = BM25Okapi([tok(f"{o['title']} {o['text'][:1500]}") for o in docs])
        s = bm.get_scores(tok(str(args.get("query", ""))))
        top = sorted(range(len(docs)), key=lambda j: -s[j])[:5]
        return json.dumps([dict(path=docs[j]["path"], title=docs[j]["title"], snippet=docs[j]["text"][:200]) for j in top])
    if name == "read_repo_adr":
        o = next((o for o in u["others"] if o["path"] == args.get("path")), None)
        return o["text"][:4000] if o else "no such ADR"
    if name == "github_activity":
        ev = [d for d in INPUTS["evidence"].get(tid, []) if d["check"] == "maintained"]
        info = tools.get(tid, {})
        return json.dumps(dict(tool=info.get("name", tid), repo=info.get("repo"), first_commit=info.get("first_commit"),
                               events=[dict(at=d["at"], what=d["title"]) for d in ev]) if info else "unknown tool")
    if name == "licence_history":
        return json.dumps([dict(at=d["at"], what=d["title"]) for d in INPUTS["evidence"].get(tid, []) if d["check"] == "open_source"]) or "[]"
    if name == "osv_advisories":
        info = tools.get(tid, {})
        if not info.get("osv_package"):
            return "no OSV package known for this tool"
        adv = info.get("osv", [])
        return json.dumps(dict(package=info["osv_package"], count=len(adv), latest=adv[-5:]))
    return "unknown tool call"


def agent(u: dict) -> dict:
    """A tool loop on Groq in JSON mode: each turn the model replies with one JSON object, either a tool call
    {"tool": name, "args": {...}} or its verdict {"verdict": ..., "why": ...}. (Groq's native tool calling with gpt-oss
    often ended a run with an empty message instead of a verdict on the dev split, so the protocol is spelled out instead.)"""
    tools_doc = "\n".join(f"- {t['name']}({', '.join(t['parameters'].get('properties', {}))}): {t['description']}" for t in AGENT_TOOLS if t["name"] != "final_answer")
    msgs = [dict(role="system", content=AGENT_SYSTEM.replace("then call final_answer once with your verdict.", "then give your verdict.") +
                 f"\nTools:\n{tools_doc}\nEach reply is one JSON object and nothing else: either {{\"tool\": \"<name>\", \"args\": {{...}}}} "
                 f"to call a tool, or {{\"verdict\": \"HOLDS\" or \"DEAD\", \"why\": \"<one sentence>\", \"evidence\": [...]}} to finish."),
            dict(role="user", content=f"Decision ({u['repo']}, decided {u['born']}): {u['title']}. Tools it picks: "
                                      f"{', '.join(INPUTS['tools'][t]['name'] for t in u['tools'])}.")]
    tin = tout = calls = 0
    ms = 0.0
    done = lambda reply: dict(reply=reply, tokens_in=tin, tokens_out=tout, tool_calls=calls, ms=round(ms))
    for step in range(9):
        body = dict(model=AGENT_MODEL, temperature=0, seed=7, max_tokens=1500, messages=msgs, response_format={"type": "json_object"},
                    reasoning_effort="low")
        r, rejected = None, None
        for attempt in range(10):
            req = urllib.request.Request(llm.GROQ_URL, data=json.dumps(body).encode(), headers={
                "content-type": "application/json", "authorization": f"Bearer {llm._env_key('GROQ_API_KEY')}", "user-agent": "moot"})
            t0 = time.perf_counter()
            try:
                r = json.loads(urllib.request.urlopen(req, timeout=120).read())
                ms += (time.perf_counter() - t0) * 1000
                break
            except urllib.error.HTTPError as e:
                detail = e.read()
                if e.code == 400 and (b"json_validate_failed" in detail or b"tool_use_failed" in detail):
                    ms += (time.perf_counter() - t0) * 1000
                    rejected = json.loads(detail)["error"].get("failed_generation") or ""
                    break
                if e.code != 429 or attempt == 9:
                    raise RuntimeError(f"Groq {e.code}: {detail[:400]!r}") from e
                wait = float(e.headers.get("retry-after") or 10)
                print(f"  rate limited, waiting {wait:.0f} s: {detail[:160]!r}", flush=True)
                time.sleep(wait)
        if r is None:
            # Groq rejected the reply; gpt-oss often emits its own tool-call format ({"name": .., "arguments": ..}) even in JSON
            # mode. Read the rejected generation as the model's turn; its tokens are not reported, so they are not counted.
            try:
                g = json.loads(rejected or "")
            except json.JSONDecodeError:
                g = {}
            a = g.get("arguments", {}) if isinstance(g, dict) else {}
            if isinstance(a, str):
                try:
                    a = json.loads(a)
                except json.JSONDecodeError:
                    a = {}
            x = a if isinstance(a, dict) and ("verdict" in a or "tool" in a) else dict(tool=g.get("name"), args=a) if isinstance(g, dict) and g.get("name") else {}
            if x.get("tool") == "final_answer" or (not x.get("tool") and "verdict" not in x):
                x = x.get("args", x) if x.get("tool") == "final_answer" else {}
            content = json.dumps(x)
            if not x:
                msgs.append(dict(role="user", content="That was not one JSON object. Reply with exactly one JSON object."))
                continue
        else:
            tin += r["usage"]["prompt_tokens"]
            tout += r["usage"]["completion_tokens"]
            content = r["choices"][0]["message"].get("content") or ""
            try:
                x = json.loads(content)
            except json.JSONDecodeError:
                x = {}
        if "verdict" in x:
            return done(content)
        if x.get("tool") and calls < 6:
            calls += 1
            msgs += [dict(role="assistant", content=content),
                     dict(role="user", content=f"Result of {x['tool']}:\n{run_tool(u, str(x['tool']), x.get('args') or {})[:6000]}")]
            continue
        msgs += [dict(role="assistant", content=content or "{}"),
                 dict(role="user", content='No more tool calls. Reply now with {"verdict": "HOLDS" or "DEAD", "why": "<one sentence>"}.')]
    return done("")


def arm_agent(fill: bool, ids: list[str]) -> dict[str, dict]:
    cache, out = _cache(AGENT_CACHE), {}
    for i in ids:
        key = hashlib.sha256(json.dumps([AGENT_MODEL, AGENT_SYSTEM, AGENT_TOOLS, i, T0]).encode()).hexdigest()[:24]
        if key not in cache and fill:
            row = dict(key=key, id=i, model=AGENT_MODEL, **agent(UNITS[i]))
            with AGENT_CACHE.open("a") as f:
                f.write(json.dumps(row) + "\n")
            cache[key] = row
            print(f"agent {i}: {_parse(row['reply'])['pred']} ({row['tool_calls']} calls, {row['tokens_in'] + row['tokens_out']} tokens)", flush=True)
        if key in cache:
            c = cache[key]
            out[i] = dict(_parse(c["reply"]), tokens_in=c["tokens_in"], tokens_out=c["tokens_out"], tool_calls=c["tool_calls"], ms=c["ms"],
                          usd=llm.price(c["model"], c["tokens_in"], c["tokens_out"]))
    return out


# ---- scoring

def score(preds: dict[str, dict], units: list[dict]) -> dict:
    n = len(units)
    have = [u for u in units if u["id"] in preds]
    right = [u for u in have if preds[u["id"]]["pred"] == u["gold"]]
    dead = [u for u in have if u["gold"] == "DEAD"]
    flagged = [u for u in have if preds[u["id"]]["pred"] == "DEAD"]
    tp = [u for u in dead if preds[u["id"]]["pred"] == "DEAD"]
    holds = [u for u in have if u["gold"] == "HOLDS"]
    tn = [u for u in holds if preds[u["id"]]["pred"] == "HOLDS"]
    rec = len(tp) / len(dead) if dead else 0.0
    spec = len(tn) / len(holds) if holds else 0.0
    return dict(n=n, answered=len(have), right=len(right), accuracy=len(right) / n if n else 0.0, accuracy_ci=wilson(len(right), n),
                dead=len(dead), caught=len(tp), recall=rec, recall_ci=wilson(len(tp), len(dead)),
                flagged=len(flagged), precision=len(tp) / len(flagged) if flagged else None,
                precision_ci=wilson(len(tp), len(flagged)) if flagged else None, holds=len(holds), held=len(tn),
                balanced_accuracy=(rec + spec) / 2)


def paired(a: dict, b: dict, units: list[dict]) -> dict:
    only_a = sum(1 for u in units if u["id"] in a and u["id"] in b and a[u["id"]]["pred"] == u["gold"] != b[u["id"]]["pred"])
    only_b = sum(1 for u in units if u["id"] in a and u["id"] in b and b[u["id"]]["pred"] == u["gold"] != a[u["id"]]["pred"])
    return dict(only_moot=only_a, only_other=only_b, p=mcnemar_exact(only_a, only_b))


LABEL = dict(moot_advisory="Moot gate, licence checks advisory (post hoc)", moot="**Moot gate (FalkorDB)**", moot_no_falkordb="Moot rules, FalkorDB removed (BM25 top 3)", majority="majority class",
             age="age ≥ 3 years", trust_adr="trust the ADR's status", rag_bm25=f"BM25 RAG + {RAG_MODEL}",
             agent_tools=f"LLM agent with GitHub/OSV tools ({AGENT_MODEL})")


def main() -> None:
    refuse_if_gold_changed()  # before anything else, so a changed answer key never reaches a score
    fill = "--llm" in sys.argv
    only = sys.argv[sys.argv.index("--split") + 1] if "--split" in sys.argv else None
    arms = sys.argv[sys.argv.index("--arms") + 1].split(",") if "--arms" in sys.argv else MODEL_ARMS
    ids = [g["id"] for g in GOLD["units"] if not only or g["split"] == only]
    every = [g["id"] for g in GOLD["units"]]
    preds = dict(moot=arm_moot(), moot_advisory=arm_moot(advisory=True), moot_no_falkordb=arm_no_falkordb(), majority=arm_majority(), age=arm_age(), trust_adr=arm_trust(),
                 rag_bm25=arm_rag(fill and "rag_bm25" in arms, ids if fill else every),
                 agent_tools=arm_agent(fill and "agent_tools" in arms, ids if fill else every))
    res = {}
    for split in ("test", "dev"):
        us = [g for g in GOLD["units"] if g["split"] == split]
        res[split] = {a: score(preds[a], us) for a in ARMS + POSTHOC}
        res[split]["paired_vs_moot"] = {a: paired(preds["moot"], preds[a], us) for a in ARMS + POSTHOC if a != "moot"}
    test = [g for g in GOLD["units"] if g["split"] == "test"]
    ag = [preds["agent_tools"][u["id"]] for u in test if u["id"] in preds["agent_tools"]]
    cost = dict(units=len(ag), tokens_in=sum(x["tokens_in"] for x in ag), tokens_out=sum(x["tokens_out"] for x in ag),
                usd=round(sum(x["usd"] for x in ag), 4), tool_calls=sum(x["tool_calls"] for x in ag),
                ms_median=sorted(x["ms"] for x in ag)[len(ag) // 2] if ag else None)
    rg = [preds["rag_bm25"][u["id"]] for u in test if u["id"] in preds["rag_bm25"]]
    rag_cost = dict(units=len(rg), seconds_median=sorted(x["seconds"] for x in rg)[len(rg) // 2] if rg else None)
    rows = [dict(id=g["id"], split=g["split"], gold=g["gold"], backed_by=g["backed_by"], **{a: preds[a].get(g["id"], {}).get("pred") for a in ARMS},
                 moot_why=preds["moot"][g["id"]]["why"]) for g in GOLD["units"]]
    # A1: what an agent asking each gatekeeper on T0 would have been allowed to do (docs/studies.md A1)
    allows = dict(moot=lambda i: preds["moot"][i]["gate"] == "ALLOW", trust_adr=lambda i: True,
                  age=lambda i: preds["age"][i]["pred"] == "HOLDS",
                  rag_bm25=lambda i: preds["rag_bm25"].get(i, {}).get("pred") == "HOLDS",
                  agent_tools=lambda i: preds["agent_tools"].get(i, {}).get("pred") == "HOLDS")
    dead_t = [u for u in test if u["gold"] == "DEAD"]
    held_t = [u for u in test if u["gold"] == "HOLDS"]
    agent_gate = {a: dict(dead_allowed=sum(f(u["id"]) for u in dead_t), dead=len(dead_t), dead_allowed_ci=wilson(sum(f(u["id"]) for u in dead_t), len(dead_t)),
                          held_blocked=sum(not f(u["id"]) for u in held_t), held=len(held_t),
                          held_blocked_ci=wilson(sum(not f(u["id"]) for u in held_t), len(held_t)))
                  for a, f in allows.items()}
    result = dict(t0=T0, end=GOLD["end"], gold_sha256=GOLD["sha256"], results=res, agent_cost=cost, rag_cost=rag_cost, rows=rows, agent_gate=agent_gate,
                  models=dict(rag_bm25=RAG_MODEL, agent_tools=AGENT_MODEL))
    (OUT / "results_heldout.json").write_text(json.dumps(result, indent=1) + "\n")
    (OUT / "results_heldout.md").write_text(markdown(result))
    t = res["test"]
    print(f"test n={t['moot']['n']}: " + ", ".join(f"{a} {t[a]['right']}/{t[a]['n']}" for a in ARMS))


def markdown(R: dict) -> str:
    t = R["results"]["test"]
    n, nd = t["moot"]["n"], t["moot"]["dead"]
    L = ["# Held-out: does this real decision still hold? (study H1)", "",
         f"Every arm sees only what existed on **{R['t0']}** and answers HOLDS or DEAD for each decision. The repositories grade it: "
         f"a decision is DEAD if, by {R['end']}, its own repository marked it superseded or deprecated, a later ADR dropped its tool, or the "
         "tool left the repository's dependency manifests or Terraform; HOLDS otherwise. Nobody on this project labelled a unit. "
         f"The gold was hashed before any arm ran (`{R['gold_sha256'][:16]}…`, eval/heldout/GOLD.sha256) and the scorer refuses to run if it changes. "
         "Prompts were fixed on the dev split; the test split ran once.", "",
         f"## Test split: {n} decisions, {nd} DEAD", "",
         "Accuracy is the primary metric. DEAD caught, false alarms, precision and balanced accuracy were registered too (docs/studies.md H1); "
         "the false-alarm column was added to the table after the first test numbers were seen. Nothing about the gold, the labels or Moot's "
         "rules changed after any test number was seen.", "",
         "| arm | right | accuracy (95% CI) | DEAD caught (recall) | false alarms (HOLDS called DEAD) | precision of DEAD calls | balanced accuracy | vs Moot (only Moot right / only it right, exact McNemar p) |",
         "|---|---|---|---|---|---|---|---|"]
    for a in ARMS:
        s = t[a]
        pv = t["paired_vs_moot"].get(a)
        prec = f"{s['caught']}/{s['flagged']} ({s['precision']:.2f})" if s["flagged"] else "no DEAD calls"
        L.append(f"| {LABEL[a]} | {s['right']}/{s['n']} | {s['accuracy']:.2f} ({s['accuracy_ci'][0]:.2f}–{s['accuracy_ci'][1]:.2f}) | "
                 f"{s['caught']}/{s['dead']} | {s['flagged'] - s['caught']}/{s['holds']} | {prec} | {s['balanced_accuracy']:.2f} | "
                 + (f"{pv['only_moot']} / {pv['only_other']}, p = {pv['p']:.3f}" if pv else "–") + " |")
    L += ["", "**Post hoc, added after the first test numbers were seen and justified on the dev split only** (4 of Moot's 5 dev false "
          "alarms were licence changes: Terraform, Consul, Elasticsearch, Kibana). It applies the rule Moot already uses for ingested "
          "repositories (licence checks are advisory unless a stated reason depends on them; commit ac86bea, written before this study's "
          "gold) to the same graph. It does not replace the frozen row above.", "",
          "| arm | right | accuracy (95% CI) | DEAD caught (recall) | false alarms (HOLDS called DEAD) | precision of DEAD calls | balanced accuracy | vs Moot (only Moot right / only it right, exact McNemar p) |",
          "|---|---|---|---|---|---|---|---|"]
    for a in POSTHOC:
        s = t[a]
        pv = t["paired_vs_moot"][a]
        prec = f"{s['caught']}/{s['flagged']} ({s['precision']:.2f})" if s["flagged"] else "no DEAD calls"
        L.append(f"| {LABEL[a]} | {s['right']}/{s['n']} | {s['accuracy']:.2f} ({s['accuracy_ci'][0]:.2f}–{s['accuracy_ci'][1]:.2f}) | "
                 f"{s['caught']}/{s['dead']} | {s['flagged'] - s['caught']}/{s['holds']} | {prec} | {s['balanced_accuracy']:.2f} | "
                 f"{pv['only_moot']} / {pv['only_other']}, p = {pv['p']:.3f} |")
    c, rc = R["agent_cost"], R["rag_cost"]
    L += ["", f"Agent cost on the test split: {c['tokens_in']:,} tokens in, {c['tokens_out']:,} out, ${c['usd']:.4f}, {c['tool_calls']} tool calls, "
              f"median {c['ms_median']} ms of model time per decision. BM25 RAG: median {rc['seconds_median']} s per decision on a local model. "
              "Moot, its FalkorDB-removed ablation and the rule baselines make no model call.", ""]
    L += ["## What an agent would have been allowed to do (study A1, test split)", "",
          "An agent asks before acting on each decision on T0. Moot's gate allows only on ALLOW (DENY and REVALIDATE block); the "
          "model arms allow on HOLDS; trust the ADR allows everything; the age rule blocks at three years. The two columns pull against "
          "each other and are never summed.", "",
          "| gatekeeper | actions on decisions that later died, allowed | actions on decisions that held, blocked |", "|---|---|---|"]
    for a, g in R["agent_gate"].items():
        L.append(f"| {LABEL[a]} | {g['dead_allowed']}/{g['dead']} ({g['dead_allowed_ci'][0]:.2f}–{g['dead_allowed_ci'][1]:.2f}) | "
                 f"{g['held_blocked']}/{g['held']} ({g['held_blocked_ci'][0]:.2f}–{g['held_blocked_ci'][1]:.2f}) |")
    L.append("")
    d = R["results"]["dev"]
    L += [f"## Dev split ({d['moot']['n']} decisions, {d['moot']['dead']} DEAD), used to fix the prompts", "",
          "| arm | right | DEAD caught | false alarms | DEAD calls |", "|---|---|---|---|---|"]
    for a in ARMS:
        L.append(f"| {LABEL[a]} | {d[a]['right']}/{d[a]['n']} | {d[a]['caught']}/{d[a]['dead']} | {d[a]['flagged'] - d[a]['caught']}/{d[a]['holds']} | {d[a]['flagged']} |")
    L += ["", "## Every test decision", "", "| decision | gold | backed by | Moot | Moot's reason | RAG | agent | age |", "|---|---|---|---|---|---|---|---|"]
    for r in R["rows"]:
        if r["split"] == "test":
            L.append(f"| {r['id']} | {r['gold']} | {', '.join(r['backed_by'])} | {r['moot']} | {r['moot_why'][:110]} | {r['rag_bm25'] or '–'} | "
                     f"{r['agent_tools'] or '–'} | {r['age']} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
