"""The backtest's answer key and evidence rules, and that the label never reaches the graph."""
import json
from pathlib import Path

from moot.backtest.labels import classify, status_text
from moot.backtest.run import maintenance_events

BT = Path(__file__).resolve().parents[1] / "data" / "backtest"


def test_status_lines_in_the_wild():
    assert classify(status_text("# 5. Use X\n\n## Status\n\nSuperseded by [ADR-0009](0009.md)\n")) == "dead"
    assert classify(status_text("Status\n------\n\nAccepted\n")) == "accepted"
    assert classify(status_text("- Status: superseded by [x](x.md)\n")) == "dead"
    assert classify(status_text("| CREATED DATE | STATUS | AUTHOR |\n| :-: | :-: | :-: |\n| 06/01/2023 | Accepted | @a |\n")) == "accepted"
    assert classify(status_text("| Status | Proposed on 2021-07-12, Accepted on 2021-08-04|\n")) == "accepted"
    assert classify(status_text("## Status\n\nInvalidated on 2021-08-04.\n")) == "dead"
    # a template that lists every option is not a death
    assert classify(status_text("**Status:** Proposed [Proposed, Accepted, Rejected, Deprecated, Superseded]")) == "proposed"
    assert classify(status_text("# Use Y\n\n## Context\n\nNo status here.")) == "none"


def test_maintenance_is_dated_when_it_became_knowable():
    ev = maintenance_events(["2019-01-01", "2019-06-01", "2021-01-01"])
    assert ev == [dict(rel="CONTRADICTS", at="2020-05-31", quote="no commit to the default branch since 2019-06-01"),
                  dict(rel="SUPPORTS", at="2021-01-01", quote="commits resume on 2021-01-01 after a gap since 2019-06-01"),
                  dict(rel="CONTRADICTS", at="2022-01-01", quote="no commit to the default branch since 2021-01-01")]
    assert maintenance_events(["2026-10-01"]) == []


def test_the_answer_key_never_enters_the_graph():
    g = json.loads((BT / "graph.json").read_text())
    assert not [e for e in g["edges"] if e["rel"] in ("RETIRES", "SUPERSEDES")]
    gates = json.loads((BT / "gates.json").read_text())
    for d in json.loads((BT / "decisions.json").read_text()):
        if d["id"] in gates and d["death"]:
            assert all(x["as_of"] < d["death"]["date"] for x in gates[d["id"]]), d["id"]


def test_evidence_is_never_dated_after_the_snapshot():
    ev = json.loads((BT / "evidence.json").read_text())
    assert all(x["at"] <= "2026-10-17" for t in ev.values() for k in ("maintained", "open_source") for x in t[k])
