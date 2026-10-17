"""End-to-end eval with a model in the loop (needs ANTHROPIC_API_KEY).

For every decision, two systems answer "Does this decision still hold? Reply with one of HOLDS, MOOT,
DISPUTED, UNDOCUMENTED, RETIRED and cite the document ids you relied on."

  rag     BM25 top-5 documents + the ADR text, handed to the model as context (a standard doc-chat company brain)
  moot    the graph verdict (no model) and Moot's narrated answer

Scored against truth.json: how often a decision whose premise was contradicted is still called HOLDS (the dead premise
treated as current), accuracy over all decisions, precision/recall for MOOT, and whether the cited documents include the
true invalidating evidence. Writes eval/results_e2e.md.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from rank_bm25 import BM25Okapi

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from moot import agent, tools  # noqa: E402
from moot.graph import graph  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
truth = json.loads((ROOT / "data" / "truth.json").read_text())
MODEL = os.getenv("MOOT_MODEL", "claude-opus-5-5")
VERDICTS = ("HOLDS", "MOOT", "DISPUTED", "UNDOCUMENTED", "RETIRED")

RAG_SYSTEM = f"""You answer questions about a company's standing decisions from the documents provided and nothing else.
Today is {truth['as_of']}. Reply with exactly one verdict word on the first line: HOLDS (the stated reason still holds),
MOOT (the stated reason no longer holds), DISPUTED (evidence conflicts), UNDOCUMENTED (no reason recorded),
RETIRED (superseded by a later decision). Then one sentence, citing document ids in square brackets."""


def tok(s):
    return re.findall(r"[a-z0-9]+", s.lower())


def main():
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set")
    import anthropic
    client = anthropic.Anthropic()
    g = graph()
    docs = truth["evidence"]
    bm25 = BM25Okapi([tok(f"{e['title']} {e['text']}") for e in docs])
    rows = []
    for d in truth["decisions"]:
        adr = (ROOT / "data" / "corpus" / d["source"]).read_text()
        scores = bm25.get_scores(tok(f"{d['title']} {d['summary']}"))
        top = [docs[i] for i in sorted(range(len(docs)), key=lambda i: -scores[i])[:5]]
        ctx = adr + "\n\n" + "\n\n".join(f"[{e['id']}] ({e['kind']}, {e['date']}) {e['title']}\n{e['text']}" for e in top)
        resp = client.messages.create(model=MODEL, max_tokens=300, system=RAG_SYSTEM,
                                      messages=[{"role": "user", "content": f"Documents:\n{ctx}\n\nQuestion: does decision {d['id']} \"{d['title']}\" still hold?"}])
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        rag_verdict = next((v for v in VERDICTS if text.upper().startswith(v)), "UNPARSED")
        rag_cites = set(re.findall(r"\[([A-Za-z0-9:_\-]+)\]", text))
        a = agent.ask(g, d["title"], truth["as_of"], 4)
        moot_verdict = a["audit"]["verdict"] if a.get("audit") else "NOT_IN_GRAPH"
        moot_cites = {e["id"] for p in a["audit"]["premises"] for e in p["evidence"]} if a.get("audit") else set()
        targets = {e["id"] for e in docs if e.get("rel") == "CONTRADICTS" and e["premise"] in _closure(d)}
        rows.append(dict(id=d["id"], expected=d["expected"], rag=rag_verdict, moot=moot_verdict, targets=sorted(targets),
                         rag_hit=bool(targets & rag_cites), moot_hit=bool(targets & moot_cites), narration=a.get("narration")))
        print(d["id"], d["expected"], "rag:", rag_verdict, "moot:", moot_verdict)

    def prf(key):
        tp = sum(1 for r in rows if r[key] == "MOOT" and r["expected"] == "MOOT")
        fp = sum(1 for r in rows if r[key] == "MOOT" and r["expected"] != "MOOT")
        fn = sum(1 for r in rows if r[key] != "MOOT" and r["expected"] == "MOOT")
        p = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        return p, rc

    n = len(rows)
    stale = [r for r in rows if r["expected"] in ("MOOT", "DISPUTED")]
    out = ["# End-to-end eval: verdicts with a model in the loop", "", f"Model: `{MODEL}`. Decisions: {n}. As of {truth['as_of']}.", "",
           f"The headline column is the stale-acceptance count: of the {len(stale)} decisions whose premise has been contradicted "
           "(expected MOOT or DISPUTED), how many did the system call HOLDS, i.e. treat the dead premise as current.", "",
           f"| system | treated a dead premise as current (of {len(stale)}) | accuracy (all verdicts) | MOOT precision | MOOT recall | cited the true invalidating doc (of decisions that have one) |",
           "|---|---|---|---|---|---|"]
    for key, label in (("rag", "BM25 RAG + model"), ("moot", "Moot (graph verdict, model narrates)")):
        acc = sum(1 for r in rows if r[key] == r["expected"]) / n
        p, rc = prf(key)
        with_t = [r for r in rows if r["targets"]]
        hit = sum(1 for r in with_t if r[f"{key}_hit"]) / len(with_t)
        accepted = [r["id"] for r in stale if r[key] == "HOLDS"]
        out.append(f"| {label} | **{len(accepted)}**{' (' + ', '.join(accepted) + ')' if accepted else ''} | {acc:.0%} | {p:.2f} | {rc:.2f} | {hit:.0%} |")
    out += ["", "| decision | expected | rag | moot | invalidating docs | rag cited one | moot cited one |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['id']} | {r['expected']} | {r['rag']} | {r['moot']} | {', '.join(r['targets'])} | {'yes' if r['rag_hit'] else 'no'} | {'yes' if r['moot_hit'] else 'no'} |")
    narrated = sum(1 for r in rows if r["narration"] == "model")
    out += ["", f"Narrations by the model that passed citation validation: {narrated}/{n}; the rest fell back to the template."]
    (ROOT / "eval" / "results_e2e.md").write_text("\n".join(out) + "\n")
    print("\n".join(out[:9]))


def _closure(d):
    pids = set(d["premises"])
    changed = True
    while changed:
        changed = False
        for p in truth["premises"]:
            if p["id"] in pids and p.get("derived_from") and p["derived_from"] not in pids:
                pids.add(p["derived_from"]); changed = True
    return pids


if __name__ == "__main__":
    main()
