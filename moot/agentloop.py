"""An agent loop over Moot's fixed tool catalogue, with claim-level citations checked in code (moot/cite.py).

The model never writes Cypher and never touches the database: it picks a tool and its arguments from a fixed catalogue,
reads the rows, and answers with claims that each quote a record a tool returned. One JSON object per reply, so it works
with any chat model, local ones included:
  {"tool": "<name>", "args": {...}}                                   call a tool (at most MAX_TOOLS per question)
  {"answer": [{"text": "...", "cite": [{"id": "...", "quote": "..."}]}, ...], "abstain": false}   finish
Unsupported claims get one repair round, then are dropped; an answer with nothing left becomes the abstention line.
"""
from __future__ import annotations

import json
from typing import Callable

from . import cite

MAX_TOOLS = 8
RESULT_CHARS = 6000

SYSTEM = """You answer questions about an organisation from its records, using the tools below; never answer from memory.
Each reply is ONE JSON object and nothing else:
- to call a tool: {"tool": "<name>", "args": {...}}
- to finish: {"answer": [{"text": "<one sentence or list item>", "cite": [{"id": "<record id from a tool result>", "quote": "<words copied exactly from that record>"}]}], "abstain": false}
Rules:
- Every claim cites at least one record a tool returned, with a quote copied word for word (at least three words, or the exact identifier).
- Give ids, links and names exactly as the records store them: all that answer the question, and only those.
- Put each item of a list in its own claim.
- If the records do not answer the question, reply {"answer": [], "abstain": true}. Do not offer near-misses.
- At most %d tool calls.""" % MAX_TOOLS


def parse(reply: str) -> dict:
    """The first JSON object in a reply."""
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


def claims_of(x: dict) -> list[dict]:
    a = x.get("answer")
    if isinstance(a, str):  # a bare sentence: no citation, so it will fail the check and get its repair round
        return [dict(text=a, cite=[])] if a.strip() else []
    return [c for c in a if isinstance(c, dict)] if isinstance(a, list) else []


def answer(question: str, tools: dict[str, Callable[[dict], object]], tool_doc: str,
           chat: Callable[[list[dict]], tuple[str, int, int, float]], context: str = "") -> dict:
    """Run one question. chat(messages) -> (reply, tokens in, tokens out, seconds).

    Returns the cleaned claims, the rendered text, whether it abstained, the validator's findings and the costs."""
    msgs = [dict(role="system", content=SYSTEM + "\nTools:\n" + tool_doc),
            dict(role="user", content=(context + "\n" if context else "") + "Question: " + question)]
    texts: dict[str, str] = {}
    used: list[str] = []
    cost = dict(tokens_in=0, tokens_out=0, seconds=0.0, calls=0)

    def turn() -> dict:
        reply, i, o, s = chat(msgs)
        cost["tokens_in"] += i
        cost["tokens_out"] += o
        cost["seconds"] += s
        msgs.append(dict(role="assistant", content=reply or "{}"))
        return parse(reply)

    final = None
    for _ in range(MAX_TOOLS + 3):
        x = turn()
        if "answer" in x or x.get("abstain") is True:
            final = x
            break
        name = str(x.get("tool", ""))
        if name in tools and cost["calls"] < MAX_TOOLS:
            cost["calls"] += 1
            used.append(name)
            try:
                res = tools[name](x.get("args") or {})
            except Exception as ex:  # a tool's own error is shown to the model, never raised
                res = {"error": str(ex)[:200]}
            cite.collect(res, texts)
            body = res if isinstance(res, str) else json.dumps(res, default=str)
            msgs.append(dict(role="user", content=f"Result of {name}:\n{body[:RESULT_CHARS]}"))
        elif name:
            msgs.append(dict(role="user", content=f"There is no tool {name!r} (or the tool budget is spent). Answer now."))
        else:
            msgs.append(dict(role="user", content='Reply with one JSON object: a tool call, or {"answer": [...], "abstain": false}.'))
    claims = claims_of(final or {})
    abstained = not final or bool(final.get("abstain")) and not claims
    problems = cite.check(claims, texts)
    first = dict(claims=len(claims), unsupported=sum(1 for p in problems if p))
    if any(problems):
        msgs.append(dict(role="user", content=cite.repair_message(claims, problems)))
        again = claims_of(turn())
        if again:
            claims, problems = again, cite.check(again, texts)
    kept = cite.clean(claims, problems)
    abstained = abstained or not kept
    searched = ", ".join(dict.fromkeys(used)) or "no tool"
    text = cite.ABSTAIN + f" Searched with: {searched}." if abstained else cite.render(kept)
    return dict(claims=[] if abstained else kept, text=text, abstained=abstained, tools=used,
                validator=dict(first, dropped=len(claims) - len(kept), repaired=first["unsupported"] > 0),
                quotes_verified=sum(len(c.get("cite") or []) for c in kept), transcript=msgs[1:], **cost)
