"""The audit agent.

Pipeline for a question:
  1. resolve the decision with the full-text index (entity resolution happens in the graph)
  2. run the audit tool: verdict, premises, evidence, owner (deterministic Cypher)
  3. check memory: a Finding written earlier, still current, means "answered from memory"
  4. narrate: a model writes the prose from the rows, and a validator rejects any decision,
     premise or evidence id in the prose that the rows did not contain
  5. if no model is configured (moot/llm.py: Groq, Anthropic or off, with a daily spend cap), a template narrates
     instead; verdicts never depend on a model
  6. UNDOCUMENTED, RETIRED and NOT_YET never reach the model: the graph's own sentence is the answer

Four outcomes, as the reference architecture asks for:
  answered_with_path | answered_from_memory | not_in_graph | unknown_entity
"""
from __future__ import annotations

import json
import re

from falkordb import Graph

from . import llm, tools

SYSTEM = """You narrate audits of company decisions for Moot. You receive JSON rows from a graph
database and nothing else. Write 3 to 6 plain sentences for an engineering lead.
Rules: state the verdict first, in the rows' own words (HOLDS, MOOT, DISPUTED, UNDOCUMENTED, RETIRED).
Name the premise and the dated evidence that decided it. Mention the owner and whether they are
still active. Mention other decisions that rest on the same expired premise if the rows list them.
Cite evidence by its id in square brackets, like [PR-412]. Never add facts that are not in the rows.
No headings, no bullet points, no markdown."""


def has_model() -> bool:
    return llm.backend() is not None


def _ids_in_rows(audit: dict, impact: list[dict]) -> set[str]:
    ids = {audit["decision"]["id"]}
    for p in audit["premises"]:
        ids.add(p["id"])
        ids.update(e["id"] for e in p["evidence"])
    if audit.get("superseded_by"):
        ids.add(audit["superseded_by"]["id"])
    for imp in impact:
        ids.update(d["id"] for d in imp.get("decisions", []))
    return ids


def validate(prose: str, allowed: set[str]) -> tuple[bool, list[str]]:
    """Every bracketed id or decision/evidence-looking token in the prose must come from the rows."""
    cited = set(re.findall(r"\[([A-Za-z0-9:_\-]+)\]", prose))
    cited |= set(re.findall(r"\b(D\d{2}|PR-\d+|[A-Z]{3,5}-\d+)\b", prose))
    bad = sorted(c for c in cited if c not in allowed)
    return (not bad, bad)


def template_narration(audit: dict, impact: list[dict]) -> str:
    d, v = audit["decision"], audit["verdict"]
    owner = audit.get("owner")
    own = ""
    if owner:
        own = f" The owner of record is {owner['name']}" + ("." if owner["active"] else f", who left on {owner['valid_to']}, so nobody owns it today.")
    if v == "RETIRED":
        s = audit["superseded_by"]
        return f"RETIRED. \"{d['title']}\" was superseded on {s['at']} by {s['id']} ({s['title']}).{own}"
    if v == "NOT_YET":
        return f"NOT YET DECIDED. As of {audit['as_of']}, \"{d['title']}\" had not been decided; it was decided on {d['decided_on']}."
    if v == "UNDOCUMENTED":
        return f"UNDOCUMENTED. \"{d['title']}\" is recorded, but the ADR states no premise, so there is nothing to check it against.{own}"
    parts = [f"{v}. \"{d['title']}\" was decided on {d['decided_on']}."]
    for p in audit["premises"]:
        if p["state"] == "expired":
            c = [e for e in p["evidence"] if e["rel"] == "CONTRADICTS"][-1]
            hop = "" if p["hops"] == 1 else f" ({p['hops']} hops from the decision)"
            early = " That evidence predates the decision, so the premise was already false when it was made." if p["contradicted_before_decision"] else ""
            parts.append(f"Its premise \"{p['text']}\"{hop} was contradicted on {c['at']} by [{c['id']}] ({c['title']}).{early}")
        elif p["state"] == "disputed":
            ev = sorted(p["evidence"], key=lambda e: e["at"])
            c = [e for e in ev if e["rel"] == "CONTRADICTS"][-1]
            s = [e for e in ev if e["rel"] == "SUPPORTS" and e["at"] >= c["at"]][-1]
            parts.append(f"Its premise \"{p['text']}\" was contradicted on {c['at']} by [{c['id']}] and re-affirmed on {s['at']} by [{s['id']}], so it is disputed rather than dead.")
        else:
            sup = [e for e in p["evidence"] if e["rel"] == "SUPPORTS"]
            parts.append(f"Its premise \"{p['text']}\" still holds" + (f"; the latest support is [{sup[-1]['id']}] on {sup[-1]['at']}." if sup else "; nothing on record contradicts it."))
    for imp in impact:
        others = [x for x in imp["decisions"] if x["id"] != d["id"]]
        if others:
            parts.append("The same premise carries " + ", ".join(f"{x['id']} ({x['title']})" for x in others) + ".")
    return " ".join(parts) + own


STRUCTURAL = ("UNDOCUMENTED", "RETIRED", "NOT_YET")


def narrate(audit: dict, impact: list[dict]) -> tuple[str, str]:
    """Returns (prose, mode) where mode is 'model', 'template' or 'structural'.

    'structural': the graph already said everything there is to say (no premise, retired, not decided yet),
    so no model is called at all. The abstention happens before the model, not inside it."""
    if audit["verdict"] in STRUCTURAL:
        return template_narration(audit, impact), "structural"
    rows = dict(audit={k: v for k, v in audit.items() if k != "found"}, shared_premises=impact)
    reply = llm.chat(SYSTEM, "Rows:\n" + json.dumps(rows, default=str), max_tokens=800)
    prose = (reply or {}).get("text", "")
    if not prose:
        return template_narration(audit, impact), "template"
    ok, bad = validate(prose, _ids_in_rows(audit, impact))
    if not ok:
        return template_narration(audit, impact) + f" (model narration rejected: cited {', '.join(bad)} which the rows did not contain)", "template"
    return prose, "model"


def ask(g: Graph, question: str, as_of: str | None = None, depth: int = 4) -> dict:
    as_of = as_of or tools.today()
    cands = tools.find_decision(g, question)
    if not cands:
        return dict(outcome="unknown_entity", question=question, answer="I could not match that question to any decision in the graph.", candidates=[])
    top = cands[0]
    audit = tools.audit_decision(g, top["id"], as_of, depth)
    if not audit["found"]:
        return dict(outcome="not_in_graph", question=question, answer="Not in the graph.", candidates=cands)
    impact = [tools.premise_impact(g, p["id"]) for p in audit["premises"] if p["state"] == "expired"]
    memory = tools.findings(g, top["id"])
    current = next((f for f in memory if not f.get("superseded_by")), None)
    # Memory may answer only while nothing the verdict rests on has changed. A Finding carries the digest of the decision's
    # whole subgraph at full depth (every premise, every dated event, retirement, owners), so evidence landing four hops
    # down also invalidates it. Findings written before digests existed fall back to the dated check on audited premises.
    if current and current.get("digest"):
        fresh = current["digest"] == tools.decision_digest(g, top["id"])
    else:
        fresh = bool(current) and current["as_of"] >= max((e["at"] for p in audit["premises"] for e in p["evidence"]), default="")
    from_memory = bool(current and fresh and current["verdict"] == audit["verdict"] and int(current.get("depth", 0)) >= depth)
    prose, mode = narrate(audit, impact)
    return dict(outcome="answered_from_memory" if from_memory else "answered_with_path", question=question,
                candidates=cands, audit=audit, impact=impact, answer=prose, narration=mode,
                memory=current, as_of=as_of, depth=depth)


def draft_ticket(audit: dict, impact: list[dict]) -> str:
    d = audit["decision"]
    lines = [f"Revisit decision {d['id']}: {d['title']}", "",
             f"Moot verdict as of {audit['as_of']}: {audit['verdict']}", ""]
    for p in audit["premises"]:
        if p["state"] in ("expired", "disputed"):
            lines.append(f"- Premise \"{p['text']}\" is {p['state']}:")
            for e in p["evidence"]:
                lines.append(f"  - {e['at']} {e['rel'].lower()} by {e['id']}: {e['title']}")
    others = sorted({x["id"] + " " + x["title"] for imp in impact for x in imp["decisions"] if x["id"] != d["id"]})
    if others:
        lines += ["", "Decisions resting on the same premise:"] + [f"- {o}" for o in others]
    owner = audit.get("owner")
    lines += ["", f"Owner of record: {owner['name'] if owner else 'none'}" + ("" if not owner or owner["active"] else f" (left {owner['valid_to']}; needs a new owner)"),
              "", "Proposed action: confirm whether the original reason still matters; if not, retire or rewrite the decision and update the ADR."]
    return "\n".join(lines)
