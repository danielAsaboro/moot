"""Real-world proof: the committed snapshot of public ADR checks, audited by the same engine. No network."""
import json

import pytest

from moot import tools
from moot.graph import DATA, connect, seed
from moot.realworld import check, records

SNAP = json.loads((DATA / "realworld" / "checks.json").read_text())


def test_snapshot_counts_are_what_the_page_claims():
    s = SNAP["summary"]
    assert s["records"] == len(SNAP["records"]) == 25 and s["repos"] == 5 and not s["dropped_records"]
    checks = [c for t in SNAP["tools"].values() for c in t["checks"].values()]
    assert s["checks"] == len(checks) and s["failing"] == sum(not c["holds"] for c in checks)
    assert s["unchecked"] == sum(len(t.get("unchecked", [])) for t in SNAP["tools"].values())


def test_go_version_mismatch_is_unchecked_not_guessed(monkeypatch):
    def fake(url, data=None, raw=False):
        if url.endswith("/repos/dexidp/dex"):
            return {"default_branch": "master", "archived": False, "license": {"spdx_id": "Apache-2.0"}}
        if "/commits" in url:
            return [{"commit": {"committer": {"date": "2026-10-01T00:00:00Z"}}}]
        if "releases/latest" in url:
            return {"tag_name": "v2.46.0"}
        if "proxy.golang.org" in url:
            return {"Version": "v0.6.1", "Time": "2021-01-01T00:00:00Z"}
        raise AssertionError(f"OSV must not be asked: {url}")
    monkeypatch.setattr(check, "_get", fake)
    r = check.check_tool("dex", "2026-10-17")
    assert "no_known_vuln" not in r["checks"] and any("does not match" in u for u in r["unchecked"])
    assert r["checks"]["maintained"]["holds"] and r["checks"]["open_source"]["holds"]


def test_stale_repo_contradicts_maintained(monkeypatch):
    def fake(url, data=None, raw=False):
        if url.endswith("/repos/olivernn/lunr.js"):
            return {"default_branch": "master", "archived": False, "license": {"spdx_id": "MIT"}}
        if "/commits" in url:
            return [{"commit": {"committer": {"date": "2020-08-19T00:00:00Z"}}}]
        if "registry.npmjs.org" in url:
            return {"dist-tags": {"latest": "2.3.9"}, "time": {"2.3.9": "2020-08-19T20:30:07Z"}}
        if "osv.dev" in url:
            return {}
        raise AssertionError(url)
    monkeypatch.setattr(check, "_get", fake)
    r = check.check_tool("lunr", "2026-10-17")
    assert r["checks"]["maintained"]["holds"] is False and r["checks"]["no_known_vuln"]["holds"] is True


def test_every_record_names_known_tools():
    for rid, repo, fn, title, d, tool_ids, quote, status in records.RECORDS:
        assert repo in records.P and all(t in records.TOOLS for t in tool_ids) and quote


@pytest.fixture(scope="module")
def pg():
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    g = db.select_graph("moot_test_public")
    seed(g, DATA / "realworld" / "graph.json", fresh=True)
    yield g
    g.delete()


def test_public_ledger_matches_the_failing_checks(pg):
    as_of = SNAP["summary"]["checked_on"]
    failing_tools = {tid for tid, t in SNAP["tools"].items() if any(not c["holds"] for c in t["checks"].values())}
    retired = {r["id"] for r in SNAP["records"] if r.get("retired")}
    expected = {r["id"] for r in SNAP["records"] if set(r["tools"]) & failing_tools} - retired
    ledger = {r["id"]: r["verdict"] for r in tools.ledger(pg, as_of, 2)}
    got = {k for k, v in ledger.items() if v == "MOOT"}
    assert got == expected and got
    # a record its own repository has retired is RETIRED, not MOOT, even though node-fetch's check fails
    assert retired == {"bs-013", "gi-0007"} and all(ledger[k] == "RETIRED" for k in retired)
    # before the check date there is no evidence, so nothing is moot: verdicts need a dated edge
    assert not [r for r in tools.ledger(pg, "2026-10-16", 2) if r["verdict"] == "MOOT"]
    # Concourse was chosen by two organisations; one premise carries both
    assert {d["id"] for d in tools.premise_impact(pg, "p_concourse_maintained")["decisions"]} == {"moj-003", "gi-0018"}


def test_retirement_is_dated(pg):
    # Backstage retired ADR013 on 2024-11-29 (ADR014); before that it was in force
    assert tools.audit_decision(pg, "bs-013", "2024-11-28", 2)["verdict"] == "HOLDS"
    a = tools.audit_decision(pg, "bs-013", SNAP["summary"]["checked_on"], 2)
    assert a["verdict"] == "RETIRED" and a["superseded_by"]["id"] == "bs-adr014" and a["superseded_by"]["at"] == "2024-11-29"


def test_unchecked_premise_is_not_reported_as_holding(pg):
    a = tools.audit_decision(pg, "gi-0004", SNAP["summary"]["checked_on"], 2)
    states = {p["id"]: p["state"] for p in a["premises"]}
    assert states["p_aws-lbc_no_known_vuln"] == "unchecked" and a["verdict"] == "HOLDS"


def test_gate_on_real_records(pg):
    on = SNAP["summary"]["checked_on"]
    lunr = tools.check_action(pg, "l4b-lunr", on)
    assert lunr["gate"] == "DENY" and lunr["reasons"][0]["evidence"] == "maintained:lunr"
    assert tools.check_action(pg, "gi-0004", on)["gate"] == "REVALIDATE"  # vulnerability check could not be answered
    assert [r["code"] for r in tools.check_action(pg, "bs-013", on)["reasons"]] == ["retired"]
    assert tools.check_action(pg, "moj-047", on)["gate"] == "ALLOW"


def test_realworld_api(pg, monkeypatch):
    from fastapi.testclient import TestClient
    from moot import api
    monkeypatch.setattr(api, "graph", lambda name=None: pg)
    r = TestClient(api.app).get("/api/realworld").json()
    assert r["summary"]["records"] == 25 and len(r["decisions"]) == 25 and r["queries"]
    lunr = next(d for d in r["decisions"] if d["id"] == "l4b-lunr")
    assert lunr["verdict"] == "MOOT" and lunr["url"].startswith("https://github.com/thomvaill/log4brains/")
