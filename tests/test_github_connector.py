"""The GitHub connector, offline: a throwaway git repository stands in for GitHub, and the API is never called."""
import json
import os
import subprocess

import pytest

from moot.connectors import github as gh
from moot.graph import connect, seed
from moot import tools

ADRS = {
    "docs/adr/0001-record-architecture-decisions.md": "# 1. Record architecture decisions\n\nDate: 2020-01-05\n\n## Status\n\nAccepted\n\n## Decision\n\nWe will use ADRs.\n",
    "docs/adr/0002-use-lunr-for-search.md": "# 2. Use Lunr for search\n\nDate: 2020-02-01\n\n## Status\n\nSuperseded by [3. Use Meilisearch](0003-use-meilisearch.md)\n\n## Decision\n\nUse Lunr.\n",
    "docs/adr/0003-use-meilisearch.md": "# 3. Use Meilisearch\n\nDate: 2021-03-01\n\n## Status\n\nAccepted\n\n## Decision\n\nUse Meilisearch for search.\n",
    "docs/adr/0004-try-graphql.md": "# 4. Try GraphQL\n\n## Status\n\nProposed\n",
    "docs/adr/README.md": "# Decisions\n",
}


def git(d, *a, env=None):
    subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True, env=env)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    d = tmp_path / "repo"
    d.mkdir()
    git(d, "init", "-q", "-b", "main")
    for i, (path, text) in enumerate(ADRS.items()):
        f = d / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
        who = ["Ada Okafor", "Kwame Mensah"][i % 2]
        git(d, "add", path)
        when = f"2021-0{i + 3}-01T00:00:00"  # the committer date is when a change landed, which the connector reads
        git(d, "-c", f"user.name={who}", "-c", "user.email=x@example.com", "commit", "-q", "-m", f"Add {path} (#{10 + i})",
            "--date", when, env=dict(os.environ, GIT_COMMITTER_DATE=when))
    monkeypatch.setattr(gh, "clone", lambda full: d)
    monkeypatch.setattr(gh, "OUT", tmp_path / "out")
    def offline(path):
        raise OSError("offline")
    monkeypatch.setattr(gh, "api", offline)
    monkeypatch.setattr(gh.rsn, "available", lambda: False)  # stated reasons have their own tests (test_reasons.py)
    gh.LOGINS.clear(); gh.NAMES.clear()
    return d


def test_finds_the_folder_and_skips_proposed_and_readme(repo):
    folder, files = gh.find_adrs(repo, None)
    assert folder == "docs/adr" and len(files) == 4 and not any("README" in f for f in files)
    s = gh.ingest("acme/app", checks=False)
    assert s["decisions"] == 3 and s["graph"] == "gh_acme_app"  # 0004 is proposed, never in force


def test_supersession_link_becomes_a_dated_edge_and_prs_are_evidence(repo):
    gh.ingest("acme/app", checks=False)
    g = json.loads(gh.load("acme/app").read_text())
    sup = [e for e in g["edges"] if e["rel"] == "SUPERSEDES"]
    assert sup == [dict(src="0003-use-meilisearch", rel="SUPERSEDES", dst="0002-use-lunr-for-search",
                        props=dict(at=sup[0]["props"]["at"], quote="Superseded by [3. Use Meilisearch](0003-use-meilisearch.md)"))]
    assert sup[0]["props"]["at"] >= "2021-03-01"  # never before the superseding ADR existed
    prs = {n["id"] for n in g["nodes"] if n["id"].startswith("pr:")}
    assert {"pr:10", "pr:11"} <= prs  # from the squash subjects, with the API offline
    owns = {e["dst"]: e["src"] for e in g["edges"] if e["rel"] == "OWNS"}
    assert owns["0001-record-architecture-decisions"] == "gh:ada-okafor" and owns["0002-use-lunr-for-search"] == "gh:kwame-mensah"


def test_successor_resolves_by_link_then_number():
    ds = {"0003-x": dict(id="0003-x"), "0007-y": dict(id="0007-y")}
    by_num = {"3": ds["0003-x"], "7": ds["0007-y"]}
    assert gh.successor_of("Superseded by [ADR](0007-y.md)", ds, by_num, "0001")["id"] == "0007-y"
    assert gh.successor_of("Superseded by ADR 3", ds, by_num, "0001")["id"] == "0003-x"
    assert gh.successor_of("Deprecated", ds, by_num, "0001") is None
    assert gh.number_of("20201103-use-lunr.md") is None and gh.number_of("adr-012-x.md") == "12"


def test_ingested_graph_audits_like_any_other(repo):
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    gh.ingest("acme/app", checks=False)
    g = db.select_graph("moot_test_gh")
    seed(g, gh.load("acme/app"), fresh=True)
    try:
        led = {r["id"]: r["verdict"] for r in tools.ledger(g, "2026-01-01", 4)}
        assert led == {"0001-record-architecture-decisions": "UNDOCUMENTED", "0002-use-lunr-for-search": "RETIRED",
                       "0003-use-meilisearch": "UNDOCUMENTED"}
        assert tools.audit_decision(g, "0002-use-lunr-for-search", "2021-01-01", 4)["verdict"] == "UNDOCUMENTED"  # before the successor
    finally:
        g.delete()


def test_api_reads_any_known_graph_and_refuses_others(monkeypatch):
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    from fastapi.testclient import TestClient
    from moot import api
    g = db.select_graph("gh_moot_test_api")
    seed(g, gh.load("thomvaill/log4brains"), fresh=True)
    api._known["at"] = 0
    try:
        c = TestClient(api.app)
        names = [x["name"] for x in c.get("/api/graphs").json()["graphs"]]
        assert names[0] == "larkspur" and "gh_moot_test_api" in names
        led = c.get("/api/ledger?graph=gh_moot_test_api&as_of=2026-10-19").json()["decisions"]
        assert {r["id"]: r["verdict"] for r in led}["20201103-use-lunr-for-search"] == "MOOT"
        assert c.get("/api/gate/20201103-use-lunr-for-search?graph=gh_moot_test_api&as_of=2026-10-19").json()["gate"] == "DENY"
        assert c.get("/api/ledger?graph=not_a_graph").status_code == 422
        assert c.get("/api/decision/D01").json()["audit"]["verdict"]  # no ?graph= is still the tenant
        monkeypatch.setenv("MOOT_ALLOW_INGEST", "0")
        assert c.post("/api/ingest/github", json={"repo": "acme/app"}).status_code == 403
    finally:
        g.delete()
        api._known["at"] = 0


def test_licence_and_vulnerability_checks_are_advisory_unless_a_stated_reason_depends_on_them():
    def payload():
        nodes = [dict(label="Premise", id=f"p_tf_{k}", props=dict(text=k, kind="unwritten", tool="tf", check=k)) for k in ("maintained", "open_source", "no_known_vuln")]
        nodes += [dict(label="Premise", id="r_a", props=dict(kind="stated", text="We chose Terraform because it is open source", quote="Terraform is open source")),
                  dict(label="Premise", id="r_b", props=dict(kind="stated", text="Many open-source projects use Terraform", quote="used by many open-source projects")),
                  dict(label="Evidence", id="open_source:tf", props=dict(kind="check")), dict(label="Evidence", id="no_known_vuln:tf", props=dict(kind="check"))]
        edges = [dict(src="open_source:tf", rel="CONTRADICTS", dst="p_tf_open_source", props=dict(at="2023-08-10")),
                 dict(src="no_known_vuln:tf", rel="CONTRADICTS", dst="p_tf_no_known_vuln", props=dict(at="2026-01-01"))]
        edges += [dict(src=r, rel="DERIVED_FROM", dst=f"p_tf_{k}", props={}) for r in ("r_a", "r_b") for k in ("maintained", "open_source", "no_known_vuln")]
        return dict(nodes=nodes, edges=edges)
    out = gh.advisory_checks(payload())
    adv = {n["id"] for n in out["nodes"] if n["props"].get("advisory")}
    assert adv == {"p_tf_open_source", "p_tf_no_known_vuln"}  # maintenance stays a hard check
    direct = [(e["src"], e["rel"], e["dst"]) for e in out["edges"] if e["props"].get("via")]
    assert direct == [("open_source:tf", "CONTRADICTS", "r_a")]  # only the reason that is about the licence, not popularity
    assert gh.advisory_checks(json.loads(json.dumps(out))) == out  # idempotent
