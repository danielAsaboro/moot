"""Read-only snapshot of the API for hosts that cannot run FalkorDB (Vercel functions).

`python -m moot.snapshot` asks the live app (backed by a running FalkorDB) every question the UI can ask at the
default date and at each month end of the rot curve, and writes the answers to data/snapshot.json. With
MOOT_SNAPSHOT=1 the app serves those recorded answers instead of querying; anything outside the recording
(another date, a ruling, an approval) gets a 503 that says to run Moot locally. Every answer in the file came
from a FalkorDB query; nothing in it is hand-written.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

from .graph import DATA

SNAPSHOT = DATA / "snapshot.json"
READ_ONLY = ("This hosted demo is a read-only snapshot of Moot's FalkorDB answers, so other dates, rulings and "
             "approvals need a live graph. Run Moot locally (make db && make seed && make serve) to try them.")


def key(method: str, path: str, query: str = "", body: dict | None = None) -> str:
    q = urlencode(sorted((k, v) for k, v in parse_qsl(query) if v != ""))
    k = f"{method} {path}" + (f"?{q}" if q else "")
    if body is not None and body.get("tool"):
        body = {k2: v for k2, v in body.items() if k2 != "question"}
    return k + (" " + json.dumps(body, sort_keys=True) if body is not None else "")


def enabled() -> bool:
    return os.getenv("MOOT_SNAPSHOT", "") not in ("", "0", "false")


def load(path: Path = SNAPSHOT) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


REF_DATE, TRAVEL_FROM = "2026-10-16", "2025-06-01"   # fixed dates the landing page asks about (frontend FeatureData.ts)
TOOLS_BY_DECISION = ("audit_decision", "check_action", "evidence_packet", "reopen_memo", "decision_owner")
VERDICTS = ("MOOT", "DISPUTED", "UNDOCUMENTED", "HOLDS", "RETIRED")


def _urls(get) -> tuple[list[str], list[str]]:
    """Every GET the UIs make: today, the landing page's fixed dates and every rot-curve month end."""
    nodes = json.loads((DATA / "graph.json").read_text())["nodes"]
    ids = {lab: [n["id"] for n in nodes if n["label"] == lab] for lab in ("Decision", "Premise", "Evidence", "Person")}
    urls = ["/api/health", "/api/schema", "/api/realworld", "/api/evals"] + [f"/api/timeline?depth={d}" for d in (1, 2, 3, 4, 5, 6)]
    points = [p["as_of"] for p in get("/api/timeline?depth=4")["points"]]
    dates = ["", REF_DATE, TRAVEL_FROM]
    views = [f"as_of={a}&depth={d}" for a in dates for d in ("", 1, 2, 3, 4, 5, 6)] + [f"as_of={a}&depth=4" for a in points] + [f"as_of={a}" for a in points]
    for v in views:
        urls += [f"/api/ledger?{v}", f"/api/orphans?{v}", f"/api/risky?{v}", f"/api/risky?{v}&limit=3"]
        urls += [f"/api/decision/{d}?{v}" for d in ids["Decision"]]
        urls += [f"/api/whatif?{v}&premise={p}" for p in ids["Premise"]]
        urls += [f"/api/whatif?{v}&q=what if we no longer need SOC 2"]
    for d in ids["Decision"]:
        urls += [f"/api/gate/{d}?as_of={a}" for a in dates + points]
        urls += [f"/api/reopen/{d}?depth=4", f"/api/document/src:{d}"]
    for d in get("/api/realworld").get("decisions", []):
        urls += [f"/api/gate/{d['id']}?graph=public_adrs", f"/api/gate/{d['id']}?as_of={REF_DATE}&graph=public_adrs"]
    urls += [f"/api/premise/{p}" for p in ids["Premise"]]
    urls += [f"/api/map?as_of={a}&depth={d}" for a in dates for d in ("", 1, 2, 3, 4, 5, 6)]   # the map scrubs months itself
    urls += [f"/api/trace/{e}" for e in ids["Evidence"]] + [f"/api/document/{e}" for e in ids["Evidence"]]
    return list(dict.fromkeys(urls)), points


def _answers(people: list[str], premises: list[str], decisions: list[str]) -> list[dict]:
    """POST /api/answer bodies: every starter question, and every follow-up (tool + input) the answer cards offer."""
    bodies = [dict(question=q, tool=None, input=None, as_of=None, depth=4) for q in _samples()]
    follow = [(t, {"decision_id": d}) for t in TOOLS_BY_DECISION for d in decisions]
    follow += [("what_if", {"reason": p}) for p in premises]
    follow += [("orphaned_decisions", {})] + [("orphaned_decisions", {"person": p}) for p in people]
    follow += [("ledger", {})] + [("ledger", {"verdict": v}) for v in VERDICTS] + [("ledger", {"owner": p}) for p in people]
    bodies += [dict(question="", tool=t, input=i, as_of=None, depth=4) for t, i in follow]
    return bodies


def build(out: Path = SNAPSHOT) -> dict:
    from fastapi.testclient import TestClient

    from .api import app

    c = TestClient(app, raise_server_exceptions=False)
    urls, points = _urls(lambda u: c.get(u).json())
    # Gates carry the as_of the UI then uses for the evidence-packet link; record those packets too.
    snap: dict[str, dict] = {}

    def record(method: str, url: str, body: dict | None = None):
        path, _, query = url.partition("?")
        r = c.post(url, json=body) if method == "POST" else c.get(url)
        if r.status_code == 200 or r.status_code == 404:
            ctype = r.headers.get("content-type", "application/json")
            snap[key(method, path, query, body)] = {"status": r.status_code, "type": ctype, "body": r.text}
        return r

    for u in urls:
        r = record("GET", u)
        if u.startswith("/api/decision/") and r.status_code == 200:
            gt = r.json().get("gate") or {}
            if gt.get("decision_id") and gt.get("as_of"):
                for fmt in ("json", "md"):
                    record("GET", f"/api/packet/{gt['decision_id']}?as_of={gt['as_of']}&format={fmt}")
    for q in _samples():
        record("POST", "/api/ask", {"question": q, "as_of": None, "depth": 4})
    nodes = json.loads((DATA / "graph.json").read_text())["nodes"]
    by = lambda lab: [n["id"] for n in nodes if n["label"] == lab]
    for b in _answers(by("Person"), by("Premise"), by("Decision")):
        r = record("POST", "/api/answer", b)
        if not b["tool"] and r.status_code == 200:  # the follow-up the starter's card points at
            t = r.json()
            if t.get("tool"):
                record("POST", "/api/answer", dict(question="", tool=t["tool"], input=t.get("input") or {}, as_of=None, depth=4))
    out.write_text(json.dumps(snap, separators=(",", ":")))
    return {"entries": len(snap), "month_ends": len(points), "bytes": out.stat().st_size}


def _samples() -> list[str]:
    import re
    root = Path(__file__).resolve().parents[1]
    out = []
    for f, marker in (("web/app.js", "const SAMPLES = ["), ("frontend/src/components/ask/AskView.tsx", "const STARTERS = ["),
                      ("frontend/src/components/landing/TryIt.tsx", "[")):
        p = root / f
        if p.exists() and marker in p.read_text():
            out += re.findall(r'"([^"]+\\?|Show the evidence for D\\d+|Which decisions are moot\\?)"', p.read_text().split(marker, 1)[1].split("];", 1)[0])
    return list(dict.fromkeys(out))


if __name__ == "__main__":
    print(build())
