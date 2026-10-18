"""Stated reasons from ADR text, offline: a fake model stands in for Ollama, and the validator decides what is kept."""
import json
import os
import subprocess

import pytest

from moot.connectors import github as gh
from moot.connectors import reasons as rsn
from moot.graph import connect, seed
from moot import tools

CAT = gh.CATALOGUE

DOC = """# 2. Implement as shell scripts

Date: 2016-02-12

## Status

Accepted

## Context

ADRs are plain text files stored in a subdirectory of the
project. The tool needs to apply small edits to the `Status` section.

## Decision

We deploy the docs site with Terraform.
"""


def test_span_survives_wrapped_lines_and_markdown_but_not_paraphrase():
    s = rsn.find_span(DOC, "ADRs are plain text files stored in a subdirectory of the project.")
    assert s and DOC[s[0]:s[1]] == "ADRs are plain text files stored in a subdirectory of the\nproject"
    assert rsn.find_span(DOC, "The tool needs to apply small edits to the Status section")  # backticks ignored
    assert rsn.find_span(DOC, "ADRs are plain-text files kept in the project") is None  # paraphrase
    assert rsn.find_span(DOC, "Accepted") is None  # too short to be a reason


def test_validator_drops_invented_title_status_and_unnamed_tool_links():
    offered = rsn.tools_named(DOC, CAT)
    assert offered == ["terraform"]
    raw = {"reasons": [
        dict(text="ADRs are plain text", quote="ADRs are plain text files stored in a subdirectory of the project", tool=None),
        dict(text="Invented", quote="The team has always loved Bash more than Python", tool=None),
        dict(text="Title", quote="Implement as shell scripts", tool=None),
        dict(text="Edits are small", quote="The tool needs to apply small edits to the Status section", tool="Terraform"),
        dict(text="Docs deploy with Terraform", quote="We deploy the docs site with Terraform", tool="Terraform"),
        dict(text="Repeat", quote="ADRs are plain text files stored in a subdirectory of the project", tool=None),
    ]}
    kept, dropped = rsn.validate_reasons("0002", "2. Implement as shell scripts", DOC, raw, CAT, offered)
    assert [r["id"] for r in kept] == ["r_0002_1", "r_0002_2", "r_0002_3"]
    assert [r["section"] for r in kept] == ["context", "context", "decision"]
    assert [r["tool"] for r in kept] == [None, None, "terraform"]  # the link survives only where the quote names the tool
    whys = [d["why"] for d in dropped]
    assert "quote is not a span of the ADR" in whys and "same span as an earlier reason" in whys
    assert any(w.startswith("tool link dropped") for w in whys)
    assert any(d.get("text") == "Title" for d in dropped)  # too short or in the title: never kept


def test_relations_must_name_a_listed_reason_and_quote_the_later_adr():
    later = "# 9. Move search to the server\n\n## Context\n\nSearch no longer runs in the browser; it moved to the API.\n"
    raw = {"relations": [
        dict(reason_id="r_0002_1", rel="CONTRADICTS", quote="Search no longer runs in the browser", why="moved"),
        dict(reason_id="r_0099_1", rel="CONTRADICTS", quote="Search no longer runs in the browser", why="unknown id"),
        dict(reason_id="r_0003_1", rel="MAYBE", quote="Search no longer runs in the browser", why="bad rel"),
        dict(reason_id="r_0003_2", rel="SUPPORTS", quote="Search is great and runs everywhere", why="invented"),
    ]}
    kept, dropped = rsn.validate_relations(later, raw, {"r_0002_1", "r_0003_1", "r_0003_2"})
    assert [(r["reason_id"], r["rel"]) for r in kept] == [("r_0002_1", "CONTRADICTS")]
    assert sorted(d["why"] for d in dropped) == ["quote is not a span of the ADR", "reason id not in the listing",
                                                 "rel is not SUPPORTS or CONTRADICTS"]


ADRS = {
    "docs/adr/0001-client-side-search.md": "# 1. Client-side search\n\nDate: 2020-01-05\n\n## Status\n\nAccepted\n\n## Context\n\n"
                                          "All of our search traffic is small enough to run in the browser.\n\n## Decision\n\nShip a search index with the site.\n",
    "docs/adr/0002-api-gateway.md": "# 2. An API gateway\n\nDate: 2021-06-01\n\n## Status\n\nAccepted\n\n## Context\n\n"
                                    "Search traffic grew tenfold and no longer fits in the browser.\n\n## Decision\n\nPut search behind the gateway.\n",
    "docs/adr/0003-use-iso-dates.md": "# 3. Use ISO dates\n\nDate: 2021-07-01\n\n## Status\n\nAccepted\n\n## Decision\n\nDates are ISO 8601.\n",
}


def fake_model(calls):
    def call(system, user):
        calls.append(user)
        if system == rsn.EXTRACT_SYSTEM:
            if "Client-side search" in user:
                return json.dumps({"reasons": [{"text": "Search traffic fits in the browser",
                                                "quote": "All of our search traffic is small enough to run in the browser.", "tool": None}]})
            if "An API gateway" in user:
                return json.dumps({"reasons": [{"text": "Search traffic is large", "quote": "Search traffic grew tenfold", "tool": None}]})
            return '{"reasons": []}'
        assert "r_0001-client-side-search_1" in user  # only reasons of earlier ADRs are listed
        return json.dumps({"relations": [{"reason_id": "r_0001-client-side-search_1", "rel": "CONTRADICTS",
                                          "quote": "Search traffic grew tenfold and no longer fits in the browser.", "why": "it no longer fits"}]})
    return call


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
        git(d, "add", path)
        when = f"2021-0{i + 7}-01T00:00:00"
        git(d, "-c", "user.name=Ada Okafor", "-c", "user.email=x@example.com", "commit", "-q", "-m", f"Add {path} (#{10 + i})",
            "--date", when, env=dict(os.environ, GIT_COMMITTER_DATE=when))
    monkeypatch.setattr(gh, "clone", lambda full: d)
    monkeypatch.setattr(gh, "OUT", tmp_path / "out")
    monkeypatch.setattr(gh, "api", lambda path: (_ for _ in ()).throw(OSError("offline")))
    monkeypatch.setattr(rsn, "available", lambda: True)
    gh.LOGINS.clear(); gh.NAMES.clear()
    return d


def test_ingest_writes_quoted_reasons_and_dated_contradictions_then_reads_them_back_without_a_model(repo, monkeypatch):
    calls = []
    monkeypatch.setattr(rsn, "call", fake_model(calls))
    s = gh.ingest("acme/app", checks=False)
    assert s["reasons"]["extracted"] == 3 and s["reasons"]["reasons"] == 2 and s["reasons"]["relations"] == 1
    g = json.loads(gh.load("acme/app").read_text())
    r1 = next(n for n in g["nodes"] if n["id"] == "r_0001-client-side-search_1")
    assert r1["props"]["kind"] == "stated" and r1["props"]["section"] == "context" and r1["props"]["extracted_by"] == rsn.model_name()
    assert r1["props"]["quote"] == "All of our search traffic is small enough to run in the browser"
    assert r1["props"]["source"].endswith("docs/adr/0001-client-side-search.md")
    c = [e for e in g["edges"] if e["rel"] == "CONTRADICTS"]
    assert c == [dict(src="src:0002-api-gateway", rel="CONTRADICTS", dst="r_0001-client-side-search_1",
                      props=dict(at="2021-06-01", quote="Search traffic grew tenfold and no longer fits in the browser", why="it no longer fits",
                                 extracted_by=rsn.model_name()))]
    first = len(calls)
    # the second build reads the cache: no model call, the same graph, byte for byte
    monkeypatch.setattr(rsn, "call", lambda *a: pytest.fail("cache miss"))
    before = gh.load("acme/app").read_text()
    gh.ingest("acme/app", checks=False, call_model=False)
    assert gh.load("acme/app").read_text() == before and first == 4  # three ADRs read, one later ADR judged


def test_without_reasons_or_model_the_connector_is_unchanged(repo, monkeypatch):
    monkeypatch.setattr(rsn, "call", lambda *a: pytest.fail("no model call when reasons are off"))
    s = gh.ingest("acme/app", checks=False, reasons=False)
    assert s["reasons"] is None
    g = json.loads(gh.load("acme/app").read_text())
    assert not [n for n in g["nodes"] if n["label"] == "Premise"]
    s = gh.ingest("acme/app", checks=False, call_model=False)  # an empty cache and no model: nothing read, nothing guessed
    assert s["reasons"]["not_read"] == 3 and s["reasons"]["reasons"] == 0


def test_a_contradicted_stated_reason_makes_the_decision_moot_from_that_day(repo, monkeypatch):
    try:
        db = connect(); db.connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    monkeypatch.setattr(rsn, "call", fake_model([]))
    gh.ingest("acme/app", checks=False)
    g = db.select_graph("moot_test_reasons")
    seed(g, gh.load("acme/app"), fresh=True)
    try:
        did = "0001-client-side-search"
        assert tools.audit_decision(g, did, "2021-01-01", 4)["verdict"] == "HOLDS"  # stated, nothing against it yet
        assert tools.check_action(g, did, "2021-01-01")["gate"] == "REVALIDATE"  # but nobody has evidence for it
        a = tools.audit_decision(g, did, "2021-06-02", 4)
        assert a["verdict"] == "MOOT" and a["premises"][0]["evidence"][0]["id"] == "src:0002-api-gateway"
        led = {r["id"]: r["verdict"] for r in tools.ledger(g, "2022-01-01", 4)}
        assert led["0003-use-iso-dates"] == "UNDOCUMENTED"  # no stated reason: still not guessed
    finally:
        g.delete()
