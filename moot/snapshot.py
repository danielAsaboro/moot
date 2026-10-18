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
    return k + (" " + json.dumps(body, sort_keys=True) if body is not None else "")


def enabled() -> bool:
    return os.getenv("MOOT_SNAPSHOT", "") not in ("", "0", "false")


def load(path: Path = SNAPSHOT) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _urls(get) -> tuple[list[str], list[dict]]:
    """Every GET the UI makes at the default date (depths 1 to 4) and at each rot-curve month end (depth 4)."""
    nodes = json.loads((DATA / "graph.json").read_text())["nodes"]
    ids = {lab: [n["id"] for n in nodes if n["label"] == lab] for lab in ("Decision", "Premise", "Evidence")}
    urls = ["/api/health", "/api/schema", "/api/realworld"] + [f"/api/timeline?depth={d}" for d in (1, 2, 3, 4, 5, 6)]
    points = [p["as_of"] for p in get("/api/timeline?depth=4")["points"]]
    views = [f"depth={d}" for d in (1, 2, 3, 4)] + [f"as_of={a}&depth=4" for a in points]
    for v in views:
        urls += [f"/api/ledger?{v}", f"/api/orphans?{v}", f"/api/risky?{v}", f"/api/risky?{v}&limit=3"]
        urls += [f"/api/decision/{d}?{v}" for d in ids["Decision"]]
        urls += [f"/api/whatif?{v}&premise={p}" for p in ids["Premise"]]
    for d in ids["Decision"]:
        urls += [f"/api/gate/{d}", f"/api/reopen/{d}?depth=4", f"/api/document/src:{d}"]
    urls += [f"/api/premise/{p}" for p in ids["Premise"]]
    urls += [f"/api/trace/{e}" for e in ids["Evidence"]] + [f"/api/document/{e}" for e in ids["Evidence"]]
    return urls, points


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
    from .api import Ask  # noqa: F401  (the sample questions the UI offers, at the default view)
    for q in _samples():
        record("POST", "/api/ask", {"question": q, "as_of": None, "depth": 4})
    out.write_text(json.dumps(snap, separators=(",", ":")))
    return {"entries": len(snap), "month_ends": len(points), "bytes": out.stat().st_size}


def _samples() -> list[str]:
    import re
    js = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text()
    block = js.split("const SAMPLES = [", 1)[1].split("];", 1)[0]
    return re.findall(r'"([^"]+)"', block)


if __name__ == "__main__":
    print(build())
