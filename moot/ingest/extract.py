"""LLM extraction: corpus documents -> decisions, premises and dated evidence with source spans.

The model proposes; a validator disposes. Every premise and every evidence relation must quote a
span that is a literal substring of the source document, or it is dropped. The output has the same
shape as truth.json so `moot build` can turn it into graph.json and the eval can score it.

Guards on what the model may write (borrowed from Hindsight's consolidator, plus the span check):
  - ids are copied from the listing, never counted or invented: a relation naming an unknown premise id is dropped
    and logged with the reason, not repaired
  - every relation carries a `reason`, kept in the output for audit
  - a reply that fails the schema is re-asked once with the errors quoted back; if it fails again, nothing from that
    document is kept (never a partial reply)
  - a stated effective date (`effective_on`) is kept only if the quote that states it is in the document; the
    document's own date stays as the statement date

Requires ANTHROPIC_API_KEY. Model: MOOT_MODEL (default claude-opus-5-5).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CORPUS = DATA / "corpus"
MODEL = os.getenv("MOOT_MODEL", "claude-opus-5-5")

ADR_SYSTEM = """You extract architecture decision records into JSON. Return only JSON with keys:
id (the ADR id, e.g. D07), title, decided_on (YYYY-MM-DD), owner_name, systems (list of strings),
summary (one sentence), premises (list of {text, quote, derived_from_quote}).
A premise is a stated reason in the Context section. `quote` is the exact sentence from the document
that states it. `derived_from_quote` is the exact "This holds because ..." sentence when the premise
depends on another stated fact, otherwise null. If the Context says no context was recorded, premises is []."""

EVIDENCE_SYSTEM = """You judge whether a document affirms or contradicts any of the listed premises.
Return only JSON: {"relations": [{"premise_id": str, "rel": "SUPPORTS"|"CONTRADICTS", "quote": str, "reason": str,
"effective_on": "YYYY-MM-DD" or null, "effective_quote": str or null}]}.
Copy `premise_id` exactly from the listing; never invent or renumber one. `quote` must be an exact substring of the
document. `reason` is one sentence on why the quote affirms or contradicts the premise. Only when the document says
the change takes effect on a different day than the document's own date, give that day as `effective_on` and the
exact sentence that says so as `effective_quote`; otherwise both are null. Only include a relation when the document
clearly states the premise still holds (SUPPORTS) or no longer holds (CONTRADICTS). Most documents touch no premise:
then return {"relations": []}."""


def _client():
    import anthropic
    return anthropic.Anthropic()


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}


def load_documents() -> list[dict]:
    docs = []
    for f in sorted((CORPUS / "adr").glob("*.md")):
        docs.append(dict(id=f.stem.split("-")[0], kind="adr", path=str(f.relative_to(DATA)), text=f.read_text(), date=None, author=None, title=f.stem))
    for f in sorted((CORPUS / "docs").glob("*.md")):
        t = f.read_text()
        date = re.search(r"Date: (\S+)", t); author = re.search(r"Author: (.+)", t); title = re.search(r"# (.+)", t)
        docs.append(dict(id=f.stem, kind="doc", path=str(f.relative_to(DATA)), text=t, date=date.group(1) if date else None,
                         author=author.group(1).strip() if author else None, title=title.group(1) if title else f.stem))
    for name, kind in (("prs.json", "pr"), ("tickets.json", "ticket")):
        for r in json.loads((CORPUS / name).read_text()):
            docs.append(dict(id=r["id"], kind=kind, path=f"corpus/{name}#{r['id']}", text=f"{r['title']}\n\n{r['body']}", date=r["date"], author=r["author"], title=r["title"]))
    for line in (CORPUS / "chat.jsonl").read_text().splitlines():
        m = json.loads(line)
        docs.append(dict(id=m["id"], kind="chat", path=f"corpus/chat.jsonl#{m['id']}", text=f"{m['channel']}: {m['text']}", date=m["ts"][:10], author=m["user"], title=f"{m['channel']} message"))
    return docs


def extract_adr(client, doc: dict) -> dict:
    resp = client.messages.create(model=MODEL, max_tokens=2000, system=ADR_SYSTEM,
                                  messages=[{"role": "user", "content": doc["text"]}])
    out = _json("".join(b.text for b in resp.content if b.type == "text"))
    kept, dropped = [], []
    for p in out.get("premises", []):
        if p.get("quote") and p["quote"] in doc["text"]:
            kept.append(p)
        else:
            dropped.append(p)
    out["premises"], out["dropped"] = kept, dropped
    return out


DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def schema_errors(out) -> list[str]:
    """Shape errors that earn a re-ask. Content errors (an unknown id, a quote not in the document) are dropped instead."""
    if not isinstance(out, dict) or not isinstance(out.get("relations"), list):
        return ['the reply must be a JSON object with a "relations" list']
    errs = []
    for i, r in enumerate(out["relations"]):
        if not isinstance(r, dict):
            errs.append(f"relations[{i}] is not an object"); continue
        for k in ("premise_id", "quote", "reason"):
            if not isinstance(r.get(k), str) or not r[k].strip():
                errs.append(f"relations[{i}].{k} must be a non-empty string")
        if r.get("rel") not in ("SUPPORTS", "CONTRADICTS"):
            errs.append(f"relations[{i}].rel must be SUPPORTS or CONTRADICTS, got {r.get('rel')!r}")
        if r.get("effective_on") is not None and not (isinstance(r["effective_on"], str) and DATE.match(r["effective_on"])):
            errs.append(f"relations[{i}].effective_on must be YYYY-MM-DD or null")
    return errs


def validate_relations(relations: list[dict], doc: dict, valid_ids: set[str]) -> tuple[list[dict], list[dict]]:
    """(kept, dropped) where every dropped relation says why. Nothing is repaired: a wrong id is not guessed at."""
    kept, dropped = [], []
    for r in relations:
        why = (f"unknown premise id {r['premise_id']!r}" if r["premise_id"] not in valid_ids else
               "quote is not in the document" if r["quote"] not in doc["text"] else
               "effective_on given without a quote from the document" if r.get("effective_on") and not (r.get("effective_quote") and r["effective_quote"] in doc["text"]) else None)
        (dropped if why else kept).append(dict(r, dropped=why) if why else r)
    return kept, dropped


def extract_evidence(client, doc: dict, premises: list[dict], log: list | None = None) -> list[dict]:
    listing = "\n".join(f"- {p['id']}: {p['text']}" for p in premises)
    msgs = [{"role": "user", "content": f"Premises:\n{listing}\n\nDocument ({doc['kind']}, {doc['date']}):\n{doc['text']}"}]
    for attempt in range(2):
        resp = client.messages.create(model=MODEL, max_tokens=1200, system=EVIDENCE_SYSTEM, messages=msgs)
        text = "".join(b.text for b in resp.content if b.type == "text")
        try:
            out = _json(text)
        except json.JSONDecodeError as ex:
            out = {"_error": str(ex)}
        errs = schema_errors(out)
        if not errs:
            break
        msgs += [{"role": "assistant", "content": text},
                 {"role": "user", "content": "Your reply failed validation:\n- " + "\n- ".join(errs) + "\nReturn the corrected JSON only."}]
    else:
        if log is not None:
            log.append(dict(doc=doc["id"], dropped="schema failed twice; nothing kept", errors=errs))
        return []
    kept, dropped = validate_relations(out["relations"], doc, {p["id"] for p in premises})
    if log is not None:
        log += [dict(doc=doc["id"], **d) for d in dropped]
    return kept


def main(limit: int | None = None, out: str = "extracted.json") -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set; extraction needs a model. The committed graph.json was built from truth.json.")
    client = _client()
    people = json.loads((CORPUS / "people.json").read_text())
    systems = json.loads((CORPUS / "systems.json").read_text())
    docs = load_documents()
    adrs = [d for d in docs if d["kind"] == "adr"][: limit or None]
    others = [d for d in docs if d["kind"] != "adr"][: limit or None]

    decisions, premises, derived = [], {}, {}
    for d in adrs:
        ex = extract_adr(client, d)
        owner = next((p["id"] for p in people if p["name"] == ex.get("owner_name")), None)
        pids = []
        for p in ex["premises"]:
            pid = "x_" + re.sub(r"[^a-z0-9]+", "_", p["text"].lower()).strip("_")[:48]
            premises.setdefault(pid, dict(id=pid, text=p["text"], kind="fact", derived_from=None))
            pids.append(pid)
            if p.get("derived_from_quote"):
                derived[pid] = p["derived_from_quote"]
        decisions.append(dict(id=ex.get("id") or d["id"], title=ex.get("title"), decided_on=ex.get("decided_on"), owner=owner or "tomi",
                              systems=[s["id"] for s in systems if s["name"] in ex.get("systems", []) or s["id"] in ex.get("systems", [])],
                              premises=pids, summary=ex.get("summary", ""), source=d["path"], dropped=ex["dropped"]))
        print(f"{d['id']}: {len(pids)} premises, {len(ex['dropped'])} dropped by the span check")
    # derived-from: the quoted "holds because" sentence names a premise that another ADR may state directly
    for pid, quote in derived.items():
        q = quote.lower()
        for other in premises.values():
            if other["id"] != pid and other["text"].lower()[:30] in q:
                premises[pid]["derived_from"] = other["id"]
    plist = list(premises.values())
    evidence, log = [], []
    for d in others:
        rels = extract_evidence(client, d, plist, log)
        author = next((p["id"] for p in people if p["name"] == d["author"]), "tomi")
        if rels:
            for r in rels:
                evidence.append(dict(id=d["id"], kind=d["kind"], date=d["date"], author=author, title=d["title"], text=d["text"][:400], rel=r["rel"],
                                     premise=r["premise_id"], quote=r["quote"], reason=r["reason"], effective_on=r.get("effective_on")))
        else:
            evidence.append(dict(id=d["id"], kind=d["kind"], date=d["date"], author=author, title=d["title"], text=d["text"][:400], rel=None, premise=None))
        print(f"{d['id']}: {[(r['rel'], r['premise_id']) for r in rels] or 'no premise touched'}")
    result = dict(as_of="2026-10-16", people=people, systems=systems, premises=plist, decisions=decisions, evidence=evidence, dropped=log)
    (DATA / out).write_text(json.dumps(result, indent=2))
    print(f"-> {DATA / out}: {len(decisions)} decisions, {len(plist)} premises, {sum(1 for e in evidence if e['rel'])} evidence relations")


if __name__ == "__main__":
    main()
