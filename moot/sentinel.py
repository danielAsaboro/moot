"""The sentinel: what changed between two dates, and should anyone be worried?

For every decision whose verdict moved between `since` and `until` it raises an alert:
  regression    held (or undocumented) on `since`, MOOT or DISPUTED on `until`: a reason broke
  retired       superseded or retired in the window
  reversal      back to HOLDS from MOOT, DISPUTED or RETIRED: someone re-affirmed it, or the retirement was undone
  new           decided inside the window
Each alert names the dated events in the window that moved it and who wrote them. A status change (SUPERSEDES, RETIRES)
also says whether its author had standing: the decision's owner or anyone above them in the reporting line, an author of its
record, or a lead of the team that answers for it, all on the event's date. A change from anyone else is not ignored but is flagged "unauthorised" for a human to
look at. A dated fact contradicting a reason needs no standing: evidence counts whoever wrote it. A
regression carries its blast radius (every other decision resting on the broken reason) and the re-open memo as a draft
follow-up; nothing is written until a person approves it (the Finding / ruling calls, as everywhere in Moot).
"""
from __future__ import annotations

from . import tools
from .tools import today

BROKEN = ("MOOT", "DISPUTED")


def _standing(g, decision_id: str, author: str | None, on: str) -> tuple[bool, str]:
    if not author:
        return True, "no author on record"
    names = {a.strip() for a in author.split(",")}
    owner = tools.decision_owner(g, decision_id, on)
    if owner and owner.get("name") in names:
        return True, f"{owner['name']} owns it"
    if owner:  # anyone up the owner's reporting line on that date
        above = {r[0] for r in tools._q(g, "MATCH path = (:Person {id: $p})-[:REPORTS_TO*1..5]->(m:Person) "
                 "WHERE all(r IN relationships(path) WHERE r.valid_from <= $on AND (r.valid_to = '' OR r.valid_to > $on)) RETURN m.name",
                 {"p": owner["id"], "on": on}).result_set}
        if names & above:
            return True, f"{', '.join(sorted(names & above))} is above its owner {owner['name']}"
    authors = {a["name"] for a in tools.decision_authors(g, decision_id, on)}
    if names & authors:
        return True, f"{', '.join(sorted(names & authors))} wrote its record"
    team = tools.decision_team(g, decision_id, on)
    leads = {x["name"] for x in (team or {}).get("leads", [])}
    if names & leads:
        return True, f"{', '.join(sorted(names & leads))} led {team['name']} then"
    return False, f"{author} is not its owner or above them, an author of its record or a lead of the team that answers for it"


def _kind(before: str, after: str) -> str | None:
    if before == after:
        return None
    if before == "NOT_YET":
        return "new"
    if after == "RETIRED":
        return "retired"
    if after in BROKEN and before not in BROKEN:
        return "regression"
    if after == "HOLDS" and before in BROKEN + ("RETIRED",):
        return "reversal"
    return "changed"


def scan(g, since: str, until: str | None = None, depth: int = 4) -> dict:
    until = until or today()
    then = {r["id"]: r["verdict"] for r in tools.ledger(g, since, depth)}
    now = {r["id"]: r for r in tools.ledger(g, until, depth)}
    alerts = []
    for did, row in now.items():
        kind = _kind(then.get(did, "NOT_YET"), row["verdict"])
        if not kind:
            continue
        a = tools.audit_decision(g, did, until, depth)
        events = [dict(e, premise=p["id"], premise_text=p["text"]) for p in a.get("premises", []) for e in p["evidence"]
                  if since < (e.get("at") or "") <= until]
        s = a.get("superseded_by")
        if s and since < (s.get("at") or "") <= until:
            if s["kind"] == "decision":  # who made the later decision: its owner on that date
                by = (tools.decision_owner(g, s["id"], s["at"]) or {}).get("name")
            else:
                by = ", ".join(r[0] for r in tools._q(g, "MATCH (p:Person)-[:AUTHORED]->(:Evidence {id: $id}) RETURN p.name", {"id": s["id"]}).result_set) or None
            events.append(dict(id=s["id"], title=s.get("title"), rel="SUPERSEDES" if s["kind"] == "decision" else "RETIRES", at=s["at"], author=by))
        for e in events:  # only a status change needs standing; a dated fact contradicting a reason is evidence from anyone
            if e.get("rel") in ("SUPERSEDES", "RETIRES"):
                e["authorised"], e["standing"] = _standing(g, did, e.get("author"), e["at"])
            else:
                e["authorised"], e["standing"] = None, "evidence: no standing needed"
        alert = dict(decision=did, title=row.get("title"), kind=kind, before=then.get(did, "NOT_YET"), after=row["verdict"],
                     events=sorted(events, key=lambda e: e["at"]), unauthorised=sum(1 for e in events if e["authorised"] is False))
        if kind == "regression":
            broken = {e["premise"] for e in events if e.get("rel") == "CONTRADICTS"}
            alert["blast_radius"] = sorted({x["id"] for p in broken for x in tools.premise_impact(g, p)["decisions"]} - {did})
            memo = tools.reopen_memo(g, did, until, depth)
            alert["draft"] = dict(text=memo.get("text"), to=memo.get("suggested_owner"), needs_approval=True)
        alerts.append(alert)
    order = {"regression": 0, "reversal": 1, "retired": 2, "changed": 3, "new": 4}
    alerts.sort(key=lambda x: (order[x["kind"]], -x["unauthorised"], x["decision"]))
    count = {k: sum(1 for x in alerts if x["kind"] == k) for k in order}
    return dict(since=since, until=until, depth=depth, alerts=alerts, counts=count,
                unauthorised=sum(x["unauthorised"] for x in alerts),
                method="two ledgers (since, until), the dated events between them, standing from OWNS, AUTHORED and LEADS on each event's date")
