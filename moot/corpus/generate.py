"""Render the Larkspur spec into a document corpus and a ground-truth file.

Output (under data/):
  corpus/adr/<id>-<slug>.md        one ADR per decision (context = stated premises)
  corpus/prs.json, tickets.json    evidence and distractors, by kind
  corpus/chat.jsonl                chat messages
  corpus/docs/<id>.md              internal documents
  corpus/people.json, systems.json
  truth.json                       the spec as data: what a perfect extractor would produce
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import prose, spec

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CORPUS = DATA / "corpus"


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def person(pid: str) -> dict:
    for p in spec.PEOPLE:
        if p[0] == pid:
            return dict(id=p[0], name=p[1], role=p[2], joined=p[3], left=p[4],
                        reports_to=[dict(manager=m, valid_from=f, valid_to=t) for (who, m, f, t) in spec.REPORTS_TO if who == pid])
    raise KeyError(pid)


def adr_markdown(d: dict) -> str:
    owner = person(d["owner"])
    pr = prose.ADR.get(d["id"], {})
    premises = [spec.PREMISES[pid][0] for pid in d["premises"]]
    lines = [f"# ADR {d['id']}: {d['title']}", "",
             f"- Status: accepted", f"- Date: {d['decided_on']}", f"- Owner: {owner['name']} ({owner['role']})",
             f"- Systems: {', '.join(d['systems'])}", ""]
    if d.get("supersedes"):
        lines += [f"- Supersedes: ADR {d['supersedes']}", ""]
    lines += ["## Context", ""]
    if pr.get("context"):
        lines.append(pr["context"].format(**{f"p{i}": t for i, t in enumerate(premises)}))
        lines.append("")
    if d["premises"]:
        lines.append("Stated premises:")
        lines.append("")
        for pid in d["premises"]:
            text, kind = spec.PREMISES[pid]
            lines.append(f"- {text}. ({kind})")
            dep = spec.DERIVED_FROM.get(pid)
            if dep:
                lines.append(f"  This holds because {spec.PREMISES[dep][0][0].lower() + spec.PREMISES[dep][0][1:]}.")
    else:
        lines.append("_No premise was recorded for this decision._")
    lines += ["", "## Decision", "", d["summary"], ""]
    if pr.get("alternatives"):
        lines += ["## Alternatives considered", ""] + [f"- {a}" for a in pr["alternatives"]] + [""]
    lines += ["## Consequences", "", pr.get("consequences", "Teams follow this until it is explicitly revisited. Exceptions need the owner's approval."), ""]
    return "\n".join(lines)


def pr_body(e: dict, rng) -> str:
    """A merged-PR description with the usual sections; the summary is the spec text verbatim."""
    sysname = e.get("system") or "service"
    changes = rng.sample(["Config change with the new value and a comment pointing at this PR", "Unit tests updated for the new behaviour",
                          "Runbook entry added", "Dashboard panel added for the affected metric", "Dead code removed", "Migration script, idempotent"], 2)
    testing = rng.choice(["Ran on staging for two days with no alerts.", "Load-tested against a copy of production traffic.",
                          "Manual check of the affected flows in staging; screenshots in the ticket.", "CI green; verified in staging by the reviewer."])
    reviewers = ", ".join(rng.sample([p[1] for p in spec.PEOPLE if p[0] != e["author"]], 2))
    return prose.PR_TEMPLATE.format(text=e["text"], changes="\n".join(f"- {c}" for c in changes), testing=testing, reviewers=reviewers)


def main() -> None:
    for sub in ("adr", "docs"):
        (CORPUS / sub).mkdir(parents=True, exist_ok=True)

    for d in spec.DECISIONS:
        (CORPUS / "adr" / f"{d['id']}-{slug(d['title'])}.md").write_text(adr_markdown(d))

    items = list(spec.EVIDENCE) + [
        dict(id=i, kind=k, date=dt, author=a, title=t, text=x, rel=None, premise=None)
        for (i, k, dt, a, t, x) in spec.DISTRACTORS + spec.noise_documents()
    ]
    items.sort(key=lambda e: e["date"])
    import random
    rng = random.Random(3)
    prs, tickets, chat = [], [], []
    for e in items:
        rec = dict(id=e["id"], date=e["date"], author=person(e["author"])["name"], title=e["title"], body=e["text"])
        if e["kind"] == "pr":
            rec["state"] = "merged"
            rec["body"] = pr_body(e, rng)
            rec["merged_by"] = rng.choice([p[1] for p in spec.PEOPLE if p[0] != e["author"]])
            prs.append(rec)
        elif e["kind"] == "ticket":
            rec["status"] = "done"
            tickets.append(rec)
        elif e["kind"] == "chat":
            channel = e["title"].split(":")[0]
            chat.append(dict(id=e["id"], ts=f"{e['date']}T10:{len(chat) % 60:02d}:00Z", channel=channel,
                             user=rec["author"], text=e["text"]))
            for n, (who, reply) in enumerate(prose.CHAT_REPLIES.get(e["id"], []), start=1):
                chat.append(dict(id=f"{e['id']}-r{n}", ts=f"{e['date']}T10:{(len(chat) + 7 * n) % 60:02d}:00Z", channel=channel,
                                 user=person(who)["name"], text=reply, reply_to=e["id"]))
        else:
            (CORPUS / "docs" / f"{e['id']}.md").write_text(
                f"# {e['title']}\n\nDate: {e['date']}  \nAuthor: {rec['author']}\n\n{e['text']}\n")
    (CORPUS / "prs.json").write_text(json.dumps(prs, indent=2))
    (CORPUS / "tickets.json").write_text(json.dumps(tickets, indent=2))
    (CORPUS / "chat.jsonl").write_text("\n".join(json.dumps(m) for m in chat) + "\n")
    (CORPUS / "people.json").write_text(json.dumps([person(p[0]) for p in spec.PEOPLE], indent=2))
    (CORPUS / "systems.json").write_text(json.dumps([dict(id=s, name=n) for s, n in spec.SYSTEMS], indent=2))

    truth = dict(
        as_of=spec.AS_OF,
        people=[person(p[0]) for p in spec.PEOPLE],
        systems=[dict(id=s, name=n) for s, n in spec.SYSTEMS],
        premises=[dict(id=k, text=v[0], kind=v[1], derived_from=spec.DERIVED_FROM.get(k)) for k, v in spec.PREMISES.items()],
        decisions=[dict(d, source=f"adr/{d['id']}-{slug(d['title'])}.md") for d in spec.DECISIONS],
        evidence=[dict(id=e["id"], kind=e["kind"], date=e["date"], author=e["author"], title=e["title"],
                       text=e["text"], rel=e["rel"], premise=e["premise"]) for e in items],
    )
    (DATA / "truth.json").write_text(json.dumps(truth, indent=2))
    print(f"corpus: {len(spec.DECISIONS)} ADRs, {len(prs)} PRs, {len(tickets)} tickets, {len(chat)} chat messages, "
          f"{len(list((CORPUS / 'docs').glob('*.md')))} docs -> {CORPUS}")


if __name__ == "__main__":
    main()
