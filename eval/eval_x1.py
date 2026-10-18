"""Study X1 (docs/studies.md): HERB, a public enterprise benchmark, scored with HERB's own evaluation code.

Arms, every one answering with the same local model:
  graph    Moot's agent loop (moot/agentloop.py) with every HERB graph tool (moot/herb_tools.py), claims checked in code
  search   the same loop, prompt and model with the search tools only (full-text search, read an artifact): no graph
  rag      BM25 over the product's artifacts, top 20, one model call
The judge is HERB's code/evaluate.py itself, loaded from data/herb/raw/code with its model call pointed at the same local
model (HERB used gpt-4o): its prompts, its normalisation, its F1. Avg is the mean of the four answerable categories.

  python3 eval/eval_x1.py --split dev [--products CollaborateForce] [--limit 20] --llm     answer and judge (fills caches)
  python3 eval/eval_x1.py --split dev                                                     score from the caches
  python3 eval/eval_x1.py --split heldout --llm     the frozen run: each product's questions are opened once, logged first

Held-out questions are read only through heldout_questions(), which appends to eval/x1/heldout_runs.log before it opens a
file; nothing else in Moot reads any product's question fields (moot/connectors/herb.py drops them on load).
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import random
import re
import sys
import time
import types
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from rank_bm25 import BM25Okapi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from moot import agentloop, herb_tools  # noqa: E402
from moot.connectors import herb  # noqa: E402

X = ROOT / "eval" / "x1"
RAW = ROOT / "data" / "herb" / "raw"
DEV = ["ExplainabilityForce", "CollaborateForce", "VizForce"]
HELDOUT = ["ContentForce", "EdgeForce", "KnowledgeForce", "MonitorForce", "SearchFlow", "SearchForce", "SummarizeForce"]
MODEL = "qwen3.8:27b"
OLLAMA = "http://localhost:11434/api/chat"
ARMS = ("graph", "search", "rag")
CATS = ("content", "person", "company", "url")


# ---- the model (local, temperature 0)

def chat(messages: list[dict], json_out: bool = False) -> tuple[str, int, int, float]:
    body = dict(model=MODEL, stream=False, think=False, messages=messages,
                options=dict(temperature=0, seed=7, num_ctx=16384, num_predict=1200))
    for attempt in range(6):
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode(), headers={"content-type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, timeout=900).read())
            return r["message"]["content"], r.get("prompt_eval_count", 0), r.get("eval_count", 0), time.perf_counter() - t0
        except Exception:
            if attempt == 5:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError


# ---- HERB's own evaluation code, with its model call pointed at the local model

def lenient_json(text: str) -> dict:
    """HERB asks for JSON in single-quoted examples; accept a JSON object or a Python-style dict."""
    for m in re.finditer(r"\{", text or ""):
        frag = text[m.start():]
        depth = 0
        for i, ch in enumerate(frag):
            depth += ch == "{"
            depth -= ch == "}"
            if depth == 0:
                cand = frag[: i + 1]
                for parse in (json.loads, ast.literal_eval):
                    try:
                        x = parse(cand)
                        if isinstance(x, dict):
                            return x
                    except Exception:
                        pass
                break
    return {}


JUDGE_CACHE = X / "judge_cache.jsonl"
_judged: dict[str, dict] = {}


def judge_call(messages, response_format="json"):
    key = hashlib.sha256(json.dumps([MODEL, messages]).encode()).hexdigest()[:24]
    if not _judged and JUDGE_CACHE.exists():
        _judged.update({r["key"]: r["out"] for r in map(json.loads, JUDGE_CACHE.read_text().splitlines())})
    if key in _judged:
        return _judged[key]
    if not FILL:
        raise LookupError("judge reply not cached")
    out = {}
    for _ in range(3):
        reply, *_ = chat(messages + [dict(role="system", content="Reply with the JSON object only.")])
        out = lenient_json(reply)
        if out:
            break
    _judged[key] = out
    with JUDGE_CACHE.open("a") as f:
        f.write(json.dumps(dict(key=key, out=out)) + "\n")
    return out


def herb_eval():
    """Import HERB's code/evaluate.py with a stand-in for its `utils.get_gpt4_response`."""
    utils = types.ModuleType("utils")
    utils.get_gpt4_response = judge_call
    sys.modules["utils"] = utils
    spec = importlib.util.spec_from_file_location("herb_evaluate", RAW / "code" / "evaluate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def judge(E, q: dict, answer: str | None) -> dict:
    """One question scored the way HERB's evaluate_answerable / evaluate_unanswerable do. A judge reply HERB's code cannot
    read (no JSON after three tries) scores 0, or counts as not declined, and is flagged."""
    try:
        return _judge(E, q, answer)
    except (KeyError, TypeError, ValueError, AttributeError):
        cat = "unanswerable" if q["kind"] == "unanswerable" else ("url" if q["type"] == "pr" else q["type"])
        return dict(category=cat, judge_failed=True, **({"declined": False} if cat == "unanswerable" else {"score": 0.0}))


def _judge(E, q: dict, answer: str | None) -> dict:
    if q["kind"] == "unanswerable":
        declined = answer is None or not E.unanswerability_eval(q["question"], answer)
        return dict(category="unanswerable", declined=bool(declined))
    text = "I don't know." if answer is None else answer
    t = q["type"]
    if t == "content":
        out = E.answer_likert_score(q["question"], q["ground_truth"], text)
        return dict(category="content", score=float(int(out)) if str(out).strip().lstrip("-").isdigit() else 0.0)
    ext = dict(person=E.answer_to_employee_ids, url=E.answer_to_urls, pr=E.answer_to_prs, company=E.answer_to_companies)[t]
    got = ext(q["question"], text) or []
    return dict(category="url" if t == "pr" else t, score=100.0 * E.f1_score_sets(got, q["ground_truth"]), extracted=got)


# ---- questions

def product_questions(path: Path, product: str) -> list[dict]:
    d = json.loads(path.read_text())
    qs = [dict(id=f"{product}:ans:{i}", product=product, kind="answerable", question=x["question"], ground_truth=x["ground_truth"],
               type=x.get("type") or x.get("question_type")) for i, x in enumerate(d.get("answerable_questions", []))]
    qs += [dict(id=f"{product}:unans:{i}", product=product, kind="unanswerable", question=x if isinstance(x, str) else x.get("question"))
           for i, x in enumerate(d.get("unanswerable_questions", []))]
    return qs


def dev_questions(products: list[str]) -> list[dict]:
    assert not set(products) & set(HELDOUT), "held-out products go through heldout_questions()"
    return [q for p in products for q in product_questions(herb.fetch(p), p)]


def heldout_questions(products: list[str], arm: str) -> list[dict]:
    X.mkdir(parents=True, exist_ok=True)
    with (X / "heldout_runs.log").open("a") as f:  # logged before any file is opened
        f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} open {','.join(products)} for arm {arm}\n")
    return [q for p in products for q in product_questions(herb.fetch(p, heldout=True), p)]


# ---- arms

def tool_doc(names: list[str]) -> str:
    out = []
    for s in herb_tools.schemas(names):
        args = ", ".join(k + ("" if k in s["parameters"].get("required", []) else "?") for k in s["parameters"]["properties"])
        out.append(f"- {s['name']}({args}): {s['description']}")
    return "\n".join(out)


def agent_arm(q: dict, names: list[str]) -> dict:
    tools = {n: (lambda a, n=n: herb_tools.call(n, dict(a, product=q["product"]) if "product" in herb_tools.TOOLS[n][2]["properties"] else a, names))
             for n in names}
    r = agentloop.answer(q["question"], tools, tool_doc(names), chat, context=f"Product: {q['product']}")
    return dict(answer=None if r["abstained"] else r["text"], abstained=r["abstained"], tokens_in=r["tokens_in"], tokens_out=r["tokens_out"],
                seconds=round(r["seconds"], 1), calls=r["calls"], tools=r["tools"], validator=r["validator"],
                quotes=r["quotes_verified"], transcript=r["transcript"])


_pools: dict[str, tuple] = {}


def rag_arm(q: dict) -> dict:
    p = q["product"]
    if p not in _pools:
        docs = herb_tools.rows(None, "MATCH (e:Evidence)-[:ABOUT]->(:Project {id: $p}) RETURN e.id AS id, coalesce(e.title, '') + ' ' + "
                                     "coalesce(e.excerpt, e.text, '') AS text", {"p": p})
        tok = lambda s: re.findall(r"[a-z0-9]+", (s or "").lower())
        _pools[p] = (docs, BM25Okapi([tok(d["text"]) for d in docs] or [["empty"]]), tok)
    docs, bm, tok = _pools[p]
    sc = bm.get_scores(tok(q["question"]))
    top = [docs[i] for i in sorted(range(len(docs)), key=lambda i: -sc[i])[:20]]
    ctx = "\n\n".join(f"[{d['id']}] {d['text'][:600]}" for d in top)
    reply, i, o, s = chat([dict(role="system", content="Answer the question from the context only. If the context does not answer it, say you don't know."),
                           dict(role="user", content=f"Product: {p}\nQuestion: {q['question']}\n\nContext:\n{ctx}")])
    return dict(answer=reply.strip() or None, tokens_in=i, tokens_out=o, seconds=round(s, 1), calls=0)


# ---- runs, caches, scores

FILL = False


def cached(arm: str, q: dict, cache: dict) -> dict | None:
    key = hashlib.sha256(json.dumps([arm, MODEL, q["id"], q["question"], agentloop.SYSTEM]).encode()).hexdigest()[:24]
    if key in cache or not FILL:
        return cache.get(key)
    try:
        r = agent_arm(q, herb_tools.GRAPH_TOOLS if arm == "graph" else herb_tools.SEARCH_TOOLS) if arm != "rag" else rag_arm(q)
    except Exception as ex:
        r = dict(answer=None, error=str(ex)[:200], tokens_in=0, tokens_out=0, seconds=0.0, calls=0)
    row = dict(key=key, arm=arm, id=q["id"], **r)
    with (X / "cache.jsonl").open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    cache[key] = row
    return row


def bootstrap_diff(a: dict, b: dict, n: int = 10000, seed: int = 7) -> tuple[float, float, float]:
    """Paired bootstrap of Avg(a) - Avg(b): resample question ids within each category, same ids for both arms."""
    rnd = random.Random(seed)
    cats = {c: [k for k in a if a[k]["category"] == c and k in b] for c in CATS}
    def avg(s, ids):
        return sum(sum(s[k]["score"] for k in ids[c]) / len(ids[c]) for c in CATS if ids[c]) / sum(1 for c in CATS if ids[c])
    point = avg(a, cats) - avg(b, cats)
    ds = []
    for _ in range(n):
        ids = {c: [rnd.choice(v) for _ in v] for c, v in cats.items()}
        ds.append(avg(a, ids) - avg(b, ids))
    ds.sort()
    return point, ds[int(0.025 * n)], ds[int(0.975 * n) - 1]


def main() -> None:
    global FILL
    FILL = "--llm" in sys.argv
    split = sys.argv[sys.argv.index("--split") + 1] if "--split" in sys.argv else "dev"
    products = sys.argv[sys.argv.index("--products") + 1].split(",") if "--products" in sys.argv else (DEV if split == "dev" else HELDOUT)
    arms = sys.argv[sys.argv.index("--arms") + 1].split(",") if "--arms" in sys.argv else list(ARMS)
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    X.mkdir(parents=True, exist_ok=True)
    cache = {r["key"]: r for r in map(json.loads, (X / "cache.jsonl").read_text().splitlines())} if (X / "cache.jsonl").exists() else {}
    E = herb_eval()
    results = {}
    for arm in arms:
        qs = heldout_questions(products, arm) if split == "heldout" else dev_questions(products)
        if limit:
            qs = [q for q in qs if int(q["id"].rsplit(":", 1)[1]) < limit]
        scored = {}
        for q in qs:
            r = cached(arm, q, cache)
            if not r:
                continue
            try:
                scored[q["id"]] = dict(judge(E, q, r.get("answer")), tokens=r["tokens_in"] + r["tokens_out"], seconds=r["seconds"])
            except LookupError:
                continue
            if FILL:
                print(arm, q["id"], json.dumps(scored[q["id"]])[:120], flush=True)
        results[arm] = scored
    lines = [f"# X1: HERB ({split}: {', '.join(products)})", "",
             f"Answer model and judge: {MODEL} (local, temperature 0). Judge: HERB's code/evaluate.py, its prompts and scoring. "
             "Content is HERB's 0 to 100 Likert score; people, customer and artifact are F1 x 100; Avg is their mean.", "",
             "| arm | Content | People | Customer | Artifact | **Avg** | unanswerable declined | answered | tokens per answer | median s |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    summary = {}
    for arm, s in results.items():
        by = {c: [x["score"] for x in s.values() if x["category"] == c] for c in CATS}
        un = [x["declined"] for x in s.values() if x["category"] == "unanswerable"]
        mean = {c: (sum(v) / len(v) if v else None) for c, v in by.items()}
        have = [v for v in mean.values() if v is not None]
        avg = sum(have) / len(have) if have else None
        secs = sorted(x["seconds"] for x in s.values())
        summary[arm] = dict(categories=mean, n={c: len(v) for c, v in by.items()}, avg=avg, declined=(sum(un) / len(un) if un else None),
                            n_unanswerable=len(un), tokens=(sum(x["tokens"] for x in s.values()) / len(s) if s else None),
                            seconds_median=secs[len(secs) // 2] if secs else None)
        f = lambda v: "–" if v is None else f"{v:.1f}"
        lines.append(f"| {arm} | " + " | ".join(f(mean[c]) for c in CATS) + f" | **{f(avg)}** | "
                     + ("–" if not un else f"{100 * sum(un) / len(un):.1f}%") + f" | {len(s)} | "
                     + ("–" if not s else f"{summary[arm]['tokens']:,.0f}") + f" | {f(summary[arm]['seconds_median'])} |")
    if "graph" in results and "search" in results and results["graph"] and results["search"]:
        ans = lambda s: {k: v for k, v in s.items() if v["category"] != "unanswerable"}
        pt, lo, hi = bootstrap_diff(ans(results["graph"]), ans(results["search"]))
        summary["graph_minus_search"] = dict(avg=pt, ci=[lo, hi])
        lines += ["", f"Graph agent minus search-only agent, Avg: {pt:+.1f} (paired bootstrap 95% interval {lo:+.1f} to {hi:+.1f}, 10,000 resamples within category)."]
    (X / f"results_{split}.json").write_text(json.dumps(dict(split=split, products=products, model=MODEL, summary=summary, per_question=results), indent=1) + "\n")
    (ROOT / "eval" / f"results_x1_{split}.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def readme_section(summary: dict) -> str:
    """The README block for the held-out result; moot verify checks it against eval/x1/results_heldout.json."""
    f = lambda v: "–" if v is None else f"{v:.1f}"
    name = dict(graph="**agent with Moot's HERB graph tools**", search="the same agent with search tools only", rag="BM25 RAG, top 20")
    rows = [f"| {name[a]} | " + " | ".join(f(summary[a]["categories"][c]) for c in CATS) + f" | **{f(summary[a]['avg'])}** | "
            + ("–" if summary[a]["declined"] is None else f"{100 * summary[a]['declined']:.1f}%") + " |" for a in ARMS if a in summary]
    d = summary.get("graph_minus_search")
    gap = (f"The graph tools are worth {d['avg']:+.1f} points of Avg over the same agent with search alone (paired bootstrap 95% "
           f"interval {d['ci'][0]:+.1f} to {d['ci'][1]:+.1f}). ") if d else ""
    return ("## HERB, a public enterprise benchmark (X1)\n\n"
            "[HERB](https://huggingface.co/datasets/Salesforce/HERB) (Salesforce AI Research) is a synthetic company of Slack threads, "
            "meetings, documents and pull requests with held-out questions. Seven products held out before any of their files was "
            "downloaded, scored by HERB's own evaluation code with the same local model as answerer and judge ([register](docs/studies.md)):\n\n"
            "| arm (qwen3.8:27b) | Content | People | Customer | Artifact | **Avg** | unanswerable declined |\n|---|---|---|---|---|---|---|\n"
            + "\n".join(rows) + "\n\n" + gap + "For reference only (a different model and judge): HERB's paper reports 32.96 for the "
            "best agentic RAG it tested. [Full table](eval/results_x1_heldout.md).\n")


def put_in_readme() -> None:
    summary = json.loads((X / "results_heldout.json").read_text())["summary"]
    p = ROOT / "README.md"
    text = p.read_text()
    block = readme_section(summary)
    if "## HERB, a public enterprise benchmark (X1)" in text:
        i = text.index("## HERB, a public enterprise benchmark (X1)")
        j = text.index("\n## ", i + 5)
        text = text[:i] + block + text[j:]
    else:
        text = text.replace("## Quickstart", block + "\n## Quickstart", 1)
    p.write_text(text)
    print("README updated with X1")


if __name__ == "__main__":
    if "--readme" in sys.argv:
        put_in_readme()
    else:
        main()
