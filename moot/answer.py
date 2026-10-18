"""Search-first answers: a question picks one read-only tool, and that tool's rows are the answer.

  1. pick the tool: with a model configured (moot/llm.py: Groq by default, a daily spend cap), the model picks from the
     list by tool call, filling in only the tool's input. It sees the question, the tool descriptions and a catalogue of
     ids read from the graph (decisions, reasons, people, systems), nothing else; it never writes Cypher and never
     touches the database, and any id it returns must be in that catalogue. With no model, over the cap, on a failure or
     on an id outside the catalogue, rules read the question instead ("can an agent…" -> check_action, "what if…" ->
     what_if, …). eval/eval_router.py measures both on questions the rules get wrong.
  2. resolve what the question is about with the graph's full-text resolvers (find_decision, find_premise), keeping
     a match only when it covers most of the question's own words, so an unrelated question gets "nothing matches".
  3. run the tool (read-only) and return its rows; the UI draws the one component that fits the tool.

The one write the answers lead to (approving a re-open memo) is a separate call, POST /api/reopen.
"""
from __future__ import annotations

import json
import re

from falkordb import Graph

from . import llm, tools

# Read-only tools an answer may run. The descriptions are what a model sees when it picks.
TOOLS: dict[str, dict] = {
    "audit_decision": dict(description="Why a decision exists and whether it still holds: its reasons, the dated evidence on each, the verdict.",
                           input={"decision_id": "Decision id, e.g. D01"}),
    "check_action": dict(description="Whether an agent may act on, enforce or change a decision: ALLOW, DENY or REVALIDATE, with the path.",
                         input={"decision_id": "Decision id"}),
    "evidence_packet": dict(description="The documents and evidence behind a decision's verdict.", input={"decision_id": "Decision id"}),
    "what_if": dict(description="What would fall if a reason broke today: every standing decision resting on it.", input={"reason": "Premise id, e.g. p_soc2_cert"}),
    "decision_owner": dict(description="Who owns a decision, and whether they are still here.", input={"decision_id": "Decision id"}),
    "orphaned_decisions": dict(description="Decisions whose owner has left, routed up the reporting line; optionally for one person.",
                               input={"person": "Person id (optional)"}),
    "reopen_memo": dict(description="Draft a memo to re-open a decision whose reason broke. Drafting writes nothing.", input={"decision_id": "Decision id"}),
    "who_knows_why": dict(description="Who knows why a decision was made: its owner, who wrote its record, who wrote evidence on its reasons; the bus factor.",
                          input={"decision_id": "Decision id"}),
    "departure": dict(description="What leaves with a person if they left: decisions nobody else here can explain, reasons only they wrote evidence on.",
                      input={"person": "Person id"}),
    "ledger": dict(description="Many decisions at once: every verdict, optionally only one verdict, one owner or one system.",
                   input={"verdict": "MOOT, DISPUTED, HOLDS, UNDOCUMENTED or RETIRED (optional)", "owner": "Person id (optional)",
                          "system": "System name, e.g. Billing (optional)"}),
}

ID = re.compile(r"\bd\s?-?0?(\d{1,2})\b", re.I)
REOPEN = re.compile(r"\b(re-?open|revisit|memo)\b")
WHATIF = re.compile(r"\bwhat if\b|\b(broke|break|breaks|stopped|no longer|turns? out)\b")
GATE = re.compile(r"\b(agents?|bots?|allowed|safe to|ok to|okay to|may (i|we)|can (i|we|an?|the)|act on|rely on|enforce|automat\w*)\b")
EVIDENCE = re.compile(r"\b(evidence|proof|prove|documents?|sources?|receipts?|citations?|cite|packet)\b")
PERSON_Q = re.compile(r"\b(own|owns|owned|left|leave|leaving|hold|held|did|decisions?|responsible|who)\b")
OWNER = re.compile(r"\b(who|owner|owns|owned|responsible|accountable)\b")
LEFT = re.compile(r"\b(left|leaver|leavers|orphan\w*)\b")
DEPART = re.compile(r"\b(leaves? with|walks? out|bus factor|if \w+ (left|leaves|quit|quits|went)|lose|loses|losing)\b")
KNOWS = re.compile(r"\bwho (else )?(knows|understands|remembers|can explain|could explain)\b")
MANY = re.compile(r"\b(which|list|everything|overview|how many)\b|\ball (the |our )?(rules|decisions)\b")
VERDICTISH = re.compile(r"\b(expired|moot|disputed|holds?|still valid|rules|decisions)\b")

# Words that say what kind of answer is wanted, not what it is about; they never pick the decision or the reason.
INTENT = set("""agent agents bot bots allowed safe ok okay may act rely enforce change changes changed evidence proof prove document documents
source sources receipt receipts citation citations cite packet who owner owns own owned responsible accountable reopen open revisit memo
broke break breaks stopped longer turn turns out decision decisions rule rules still hold holds valid moot expired disputed anymore show
tell can need needs needed behind about""".split())


def _words(q: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", q.lower()) if w not in tools.STOP and w not in INTENT and len(w) > 2]


def _stem(w: str) -> str:
    for end in ("ing", "ed", "es", "s"):
        if w.endswith(end) and len(w) - len(end) >= 4:
            return w[: -len(end)]
    return w


def _covers(cand: dict, words: list[str], key: str) -> bool:
    """Keep a resolver hit only when it covers most of the question's own words (and at least one)."""
    if not words:
        return False
    hay = cand[key].lower() + " " + (cand.get("summary") or "").lower()
    hits = sum(1 for w in words if w in hay or _stem(w) in hay)
    return hits >= 1 and hits / len(words) >= 0.4


def _decision(g: Graph, q: str) -> tuple[str | None, str | None]:
    m = ID.search(q)
    if m:
        did = f"D{int(m.group(1)):02d}"
        if tools._q(g, "MATCH (d:Decision {id: $id}) RETURN d.id", {"id": did}).result_set:
            return did, None
    words = _words(q)
    if not words:
        return None, None
    for c in tools.find_decision(g, " ".join(words)):
        if _covers(c, words, "title"):
            return c["id"], c["title"]
    return None, None


def _premise(g: Graph, q: str) -> tuple[str | None, str | None]:
    words = [w for w in _words(q) if w not in tools.WHATIF_STOP]
    if not words:
        return None, None
    for c in tools.find_premise(g, " ".join(words)):
        if _covers(c, words, "text"):
            return c["id"], c["text"]
    return None, None


def _people(g: Graph) -> list[dict]:
    rows = tools._q(g, "MATCH (p:Person) RETURN p.id, p.name, p.left ORDER BY p.id").result_set
    return [dict(id=r[0], name=r[1], left=r[2] or "") for r in rows]


def _person(g: Graph, q: str) -> dict | None:
    t = q.lower()
    for p in _people(g):
        first = p["name"].split()[0].lower()
        if p["name"].lower() in t or re.search(rf"\b{re.escape(first)}\b", t):
            return p
    return None


def route(g: Graph, question: str, as_of: str) -> dict:
    """Rules: question -> {tool, input, why, matched}. tool None means nothing in the graph matches."""
    t = question.lower()
    person = _person(g, question)
    did, title = _decision(g, question)
    matched = f"matched “{title}”" if title else None
    if REOPEN.search(t) and did:
        return dict(tool="reopen_memo", input={"decision_id": did}, why="the question asks to re-open a decision", matched=matched)
    if WHATIF.search(t):
        pid, text = _premise(g, question)
        if not pid and did:
            first = next((p for p in tools.audit_decision(g, did, as_of)["premises"] if p["hops"] == 1), None)
            pid, text = (first["id"], first["text"]) if first else (None, None)
        if pid:
            return dict(tool="what_if", input={"reason": pid}, why="the question supposes a reason breaks", matched=f"matched the reason “{text}”")
    if GATE.search(t) and did:
        return dict(tool="check_action", input={"decision_id": did}, why="the question asks whether an agent may act", matched=matched)
    if EVIDENCE.search(t) and did:
        return dict(tool="evidence_packet", input={"decision_id": did}, why="the question asks for the evidence", matched=matched)
    if person and DEPART.search(t):
        return dict(tool="departure", input={"person": person["id"]}, why="the question asks what leaves with someone", matched=f"matched {person['name']}")
    if KNOWS.search(t) and did:
        return dict(tool="who_knows_why", input={"decision_id": did}, why="the question asks who knows why", matched=matched)
    if person and PERSON_Q.search(t):
        if person["left"]:
            return dict(tool="orphaned_decisions", input={"person": person["id"]}, why="the question is about someone who left", matched=f"matched {person['name']}")
        return dict(tool="ledger", input={"owner": person["id"]}, why="the question is about what someone owns", matched=f"matched {person['name']}")
    if OWNER.search(t) and did:
        return dict(tool="decision_owner", input={"decision_id": did}, why="the question asks who owns it", matched=matched)
    if LEFT.search(t):
        return dict(tool="orphaned_decisions", input={}, why="the question is about people who left", matched=None)
    if not ID.search(question) and (MANY.search(t) or (not did and VERDICTISH.search(t))):
        v = ("DISPUTED" if re.search(r"\bdisputed\b", t) else "HOLDS" if re.search(r"\b(holds?|valid)\b", t)
             else "MOOT" if re.search(r"\b(moot|expired|stale|dead)\b", t) else None)
        return dict(tool="ledger", input={"verdict": v} if v else {}, why="the question is about many decisions", matched=None)
    if did:
        return dict(tool="audit_decision", input={"decision_id": did}, why="the question asks why a rule exists", matched=matched)
    if person:
        return route(g, f"what did {person['name']} own", as_of)
    return dict(tool=None, input={}, why="nothing in the graph matches the question", matched=None)


ROUTER_SYSTEM = """You route one question about a company's standing decisions to the one read-only tool that answers it.
Call exactly one tool. Fill its inputs only with ids from the catalogue in the user message (decision ids like D07,
reason ids like p_eu_market, person ids like priya, system names exactly as listed); never invent one.
- why a rule exists, whether it still holds, whether it is still right -> audit_decision
- whether someone (a person, an agent, a bot) may do something a decision forbids or requires -> check_action on that decision
- who owns or decided one decision -> decision_owner; who owns an area or system -> ledger with system
- who knows, understands or can explain why -> who_knows_why
- "what if", "suppose", "what happens if" a fact stops being true -> what_if on the reason that fact is
- what someone owns or looks after -> ledger with owner; what is stale, broken or worth revisiting -> ledger with verdict MOOT
- the documents, paper trail or proof -> evidence_packet; a case or memo to reconsider -> reopen_memo
- what is lost if a person leaves -> departure; decisions whose owner left -> orphaned_decisions"""

CATALOGUE_CAP = 120  # decisions and reasons listed to the model; a bigger graph lists the full-text matches first


def _catalogue(g: Graph, question: str) -> dict:
    """Everything the model may name, read from the graph: decision titles, reason texts, people, systems."""
    words = " ".join(_words(question)) or question
    first = [c["id"] for c in tools.find_decision(g, words)] + [c["id"] for c in tools.find_premise(g, words)]
    dec = [dict(id=r[0], title=r[1]) for r in tools._q(g, "MATCH (d:Decision) RETURN d.id, d.title ORDER BY d.id").result_set]
    rea = [dict(id=r[0], text=r[1]) for r in tools._q(g, "MATCH (p:Premise) RETURN p.id, p.text ORDER BY p.id").result_set]
    rank = {i: n for n, i in enumerate(first)}
    dec.sort(key=lambda c: rank.get(c["id"], len(rank)))
    rea.sort(key=lambda c: rank.get(c["id"], len(rank)))
    systems = [r[0] for r in tools._q(g, "MATCH (s:System) RETURN s.name ORDER BY s.name").result_set]
    return dict(decisions=dec[:CATALOGUE_CAP], reasons=rea[:CATALOGUE_CAP],
                people=[dict(id=p["id"], name=p["name"], left=bool(p["left"])) for p in _people(g)], systems=systems)


def route_model(g: Graph, question: str, as_of: str) -> dict | None:
    """A model picks the tool from the same list (moot/llm.py: Groq by default, with a daily spend cap). It sees the tool
    descriptions and a catalogue of ids read from the graph; any input that is not in the catalogue is rejected and the
    rules answer instead. None means: use the rules."""
    if llm.backend() is None:
        return None
    cat = _catalogue(g, question)
    allowed = dict(decision_id={c["id"] for c in cat["decisions"]}, reason={c["id"] for c in cat["reasons"]},
                   person={p["id"] for p in cat["people"]}, owner={p["id"] for p in cat["people"]}, system=set(cat["systems"]),
                   verdict={"MOOT", "DISPUTED", "HOLDS", "UNDOCUMENTED", "RETIRED"})
    specs = [dict(name=n, description=t["description"],
                  parameters=dict(type="object", properties={k: dict(type="string", description=v) for k, v in t["input"].items()}))
             for n, t in TOOLS.items()]
    reply = llm.chat(ROUTER_SYSTEM, f"Question: {question}\nCatalogue: {json.dumps(cat)}", tools=specs, max_tokens=400)
    call = (reply or {}).get("tool")
    if not call or call["name"] not in TOOLS:
        return None
    inp = {k: str(v) for k, v in (call.get("input") or {}).items() if k in TOOLS[call["name"]]["input"] and v not in (None, "")}
    if any(v not in allowed[k] for k, v in inp.items()):
        return None
    need = dict(audit_decision="decision_id", check_action="decision_id", evidence_packet="decision_id", decision_owner="decision_id",
                reopen_memo="decision_id", who_knows_why="decision_id", departure="person", what_if="reason").get(call["name"])
    if need and need not in inp:
        return None
    return dict(tool=call["name"], input=inp, why=f"{reply['model']} picked it from the tool list", matched=None,
                model=dict(name=reply["model"], tokens_in=reply["tokens_in"], tokens_out=reply["tokens_out"],
                           usd=round(reply["usd"], 6), ms=reply.get("ms"), cached=reply.get("cached", False)))


def run(g: Graph, tool: str, inp: dict, as_of: str, depth: int) -> dict:
    """Run one read-only tool. Raises KeyError for a tool that is not on the list."""
    if tool == "audit_decision":
        return tools.audit_decision(g, inp["decision_id"], as_of, depth)
    if tool == "check_action":
        return tools.check_action(g, inp["decision_id"], as_of)
    if tool == "evidence_packet":
        # the exhibit cards are drawn from the audit's evidence rows, so the answer carries both
        return dict(tools.evidence_packet(g, inp["decision_id"], as_of), audit=tools.audit_decision(g, inp["decision_id"], as_of, depth))
    if tool == "what_if":
        return tools.what_if(g, inp["reason"], as_of, depth)
    if tool == "decision_owner":
        audit = tools.audit_decision(g, inp["decision_id"], as_of, depth)
        owner = tools.decision_owner(g, inp["decision_id"], as_of)
        orphans = tools.orphans(g, as_of, depth) if owner and not owner.get("active", True) else None
        group = next((gr for gr in (orphans or {}).get("groups", []) if gr["person"]["id"] == owner["id"]), None) if owner else None
        return dict(found=audit["found"], decision=audit.get("decision"), owner=owner, group=group, team=audit.get("team"),
                    held=[r for r in tools.ledger(g, as_of, depth) if owner and r.get("owner_id") == owner["id"]])
    if tool == "orphaned_decisions":
        r = tools.orphans(g, as_of, depth)
        if inp.get("person"):
            r["groups"] = [gr for gr in r["groups"] if gr["person"]["id"] == inp["person"]]
        return r
    if tool == "reopen_memo":
        m = tools.reopen_memo(g, inp["decision_id"], as_of, depth)
        return dict(m, audit=tools.audit_decision(g, inp["decision_id"], as_of, depth)) if m.get("found") else m
    if tool == "who_knows_why":
        from . import people
        return dict(people.knowers(g, inp["decision_id"], as_of), audit=tools.audit_decision(g, inp["decision_id"], as_of, depth))
    if tool == "departure":
        from . import people
        return people.departure(g, inp["person"], as_of)
    if tool == "ledger":
        rows = tools.ledger(g, as_of, depth)
        person = next((p for p in _people(g) if p["id"] == inp.get("owner")), None)
        if inp.get("verdict"):
            rows = [r for r in rows if r["verdict"] == inp["verdict"]]
        if person:
            rows = [r for r in rows if r.get("owner_id") == person["id"]]
        if inp.get("system"):
            rows = [r for r in rows if inp["system"] in (r.get("systems") or [])]
        return dict(as_of=as_of, depth=depth, decisions=rows, verdict=inp.get("verdict"), owner=person, system=inp.get("system"))
    raise KeyError(tool)


def answer(g: Graph, question: str, as_of: str | None = None, depth: int = 4, tool: str | None = None, inp: dict | None = None) -> dict:
    """The whole exchange. Pass `tool` and `inp` to skip picking (a follow-up the UI already knows)."""
    as_of = as_of or tools.today()
    if tool:
        if tool not in TOOLS:
            raise KeyError(tool)
        picked = dict(tool=tool, input={k: v for k, v in (inp or {}).items() if k in TOOLS[tool]["input"] and v}, why="you picked this follow-up",
                      matched=None, picked_by="you")
    else:
        picked = route_model(g, question, as_of)
        picked = dict(picked, picked_by="model") if picked else dict(route(g, question, as_of), picked_by="rules")
    out = dict(question=question, as_of=as_of, depth=depth, **picked)
    if picked["tool"] is None:
        return dict(out, result=None)
    return dict(out, result=run(g, picked["tool"], picked["input"], as_of, depth))
