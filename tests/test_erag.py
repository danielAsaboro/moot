"""EnterpriseRAG-Bench blind path: it must never read the answer key, and the cut must keep the budget."""
import ast
import json
import sqlite3
from pathlib import Path

import pytest

from moot.bench_erag import TOP_K, extract

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

PKG = Path(__file__).resolve().parents[1] / "moot" / "bench_erag"
BLIND_MODULES = ("corpus.py", "pools.py", "extract.py", "extract_v2.py", "extract_v3.py", "extract_v3_groq.py", "extract_v3_local38.py", "graph.py",
                 "cut.py")
GOLD = ("expected_doc_ids", "gold_doc_ids", "gold_answer", "answer_facts", "load_gold", "oracle", "conflict_inventory",
        "old_doc_id", "new_doc_id")
POISON = "GOLD-POISON-7f3a"


def names_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.add(node.value)
        elif isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.alias):
            out.update(node.name.split("."))
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.update(node.module.split("."))
    return out


@pytest.mark.parametrize("module", BLIND_MODULES)
def test_blind_modules_never_name_a_gold_field(module):
    found = {n for n in names_in(PKG / module) for g in GOLD if g in n}
    assert not found, f"{module} references the answer key: {found}"


def test_load_blind_reads_two_columns_and_never_the_answer_key(tmp_path, monkeypatch):
    from moot.bench_erag import questions
    path = tmp_path / "q.parquet"
    pq.write_table(pa.table(dict(question_id=["q1"], question_type=["conflicting_info"], question=["what is the burst reservation?"],
                                 expected_doc_ids=[[POISON]], gold_answer=[POISON], answer_facts=[[POISON]])), path)
    asked = []
    real = pq.read_table
    monkeypatch.setattr(pq, "read_table", lambda p, columns=None, **k: asked.append(columns) or real(p, columns=columns, **k))
    rows = questions.load_blind(path)
    assert asked == [list(questions.BLIND_COLUMNS)]
    assert POISON not in json.dumps(rows)


def test_blind_pipeline_end_to_end_never_sees_the_answer_key(tmp_path, monkeypatch):
    """pools -> extract on a tiny corpus, with the answer key poisoned and every parquet read recorded."""
    from moot.bench_erag import corpus, pools, questions
    qpath = tmp_path / "questions.parquet"
    pq.write_table(pa.table(dict(
        question_id=["q1"], question_type=["conflicting_info"],
        question=["What share of interactive burst credits is reserved for priority=high routes on dp-1?"],
        expected_doc_ids=[[POISON]], gold_answer=[POISON], answer_facts=[[POISON]])), qpath)
    dpath = tmp_path / "documents.parquet"
    pq.write_table(pa.table(dict(
        doc_id=["old", "new", "other"], source_type=["jira", "google_drive", "slack"], title=["dp-1 burst", "dp-1 burst update", "lunch"],
        content=["2026-03-11 suggested_next_steps: reserve 20% of interactive burst credits exclusively for priority=high routes on dp-1.",
                 "2026-03-12 Updated reservation target: reserve 30% (previous internal suggestion was 20%) of interactive burst "
                 "credits exclusively for priority=high routes on dp-1. Applied.",
                 "pizza at noon"])), dpath)
    monkeypatch.setattr(questions, "DATA", tmp_path)
    monkeypatch.setattr(pools, "PATH", tmp_path / "pools.json")
    db = tmp_path / "corpus.sqlite"
    corpus.build(dpath, db)
    monkeypatch.setattr(pools, "Corpus", lambda: corpus.Corpus(db))
    asked = []
    real = pq.read_table
    monkeypatch.setattr(pq, "read_table", lambda p, columns=None, **k: asked.append(columns) or real(p, columns=columns, **k))
    p = pools.build()
    c = corpus.Corpus(db)
    edges = extract.edges(p["q1"]["question"], {d: c.doc(d).content for d in p["q1"]["ranking"]})
    assert asked == [list(questions.BLIND_COLUMNS)], "the blind path read more than question_id and question"
    blob = json.dumps(p) + json.dumps([e.__dict__ if hasattr(e, "__dict__") else str(e) for e in edges]) + (tmp_path / "pools.json").read_text()
    assert POISON not in blob
    assert [(e.new_doc, e.old_doc, e.old, e.new) for e in edges] == [("new", "old", "20%", "30%")]


def test_fill_keeps_the_budget_and_never_readmits():
    from moot.bench_erag.cut import fill
    ranking = [f"d{i}" for i in range(30)]
    assert fill(ranking, set()) == ranking[:TOP_K]
    out = fill(ranking, {"d0", "d3", "d12"})
    assert len(out) == TOP_K and not {"d0", "d3", "d12"} & set(out) and out[-1] == "d11"


def test_rules_leave_measurements_ramps_and_proposals_alone():
    assert extract.statements("x", "p99 latency dropped from 1800ms -> 420ms after the fix.") == []
    assert extract.statements("x", "Rollout: 1% -> 5% -> 25% -> 100% over a week.") == []
    assert extract.statements("x", "Maybe we should move the TTL from 600s to 120s?") == []
    s = extract.statements("x", "Discount: APPROVED at 20% (not 30%) for year 1 only")
    assert [(t.old, t.new) for t in s] == [("30%", "20%")]


def test_mutual_retirement_is_a_contradiction_not_a_supersession():
    a = "2026-01-01 The cap for tenant acme-1 batch window was changed from 50ms to 20ms and applied to tenant acme-1 batch window."
    b = "2026-01-01 The cap for tenant acme-1 batch window was changed from 20ms to 50ms and applied to tenant acme-1 batch window."
    assert extract.edges("batch window cap for tenant acme-1", {"a": a, "b": b}) == []


def test_judged_summary_counts_runs_ranges_and_the_paired_interval():
    from moot.bench_erag.answer import summarise
    gold = {f"q{i}": dict(question_type="conflicting_info" if i < 4 else "info_not_found") for i in range(8)}
    qids = sorted(gold)
    base = [{q: i % 2 == 0 for i, q in enumerate(qids)}] * 3
    moot = [{q: True for q in qids}, {q: True for q in qids}, {q: q != "q0" for q in qids}]
    out = summarise(dict(baseline=base, moot=moot), dict(baseline=[0, 0, 0], moot=[0, 1, 0]), gold, qids)
    text = "\n".join(out["lines"])
    assert "| baseline | 2.0 (2–2) | 2.0 (2–2) | 4.0 (4–4) | 0 |" in text
    assert "| moot | 3.7 (3–4) | 4.0 (4–4) | 7.7 (7–8) | 1 |" in text
    assert "moot − baseline" in text


def test_v3_pairs_by_rules_and_never_lets_the_model_drop(monkeypatch):
    """The model only reports values; the rules decide. Same value is never a conflict; mutual wins cancel."""
    from moot.bench_erag import extract_v3
    seen = []
    reply = {"docs": [
        {"doc": 1, "value": "20%", "status": "superseded", "replaces": None, "date": "2026-03-11"},
        {"doc": 2, "value": "30% of burst credits", "status": "current", "replaces": "20%", "date": "2026-03-12"},
        {"doc": 3, "value": "30 %", "status": "current", "replaces": None, "date": "2026-01-01"},
        {"doc": 4, "value": None, "status": None, "replaces": None, "date": None}]}
    monkeypatch.setattr(extract_v3, "ask", lambda prompt: seen.append(prompt) or reply)
    docs = {"a": "old", "b": "new", "c": "same", "d": "none"}
    es = extract_v3.edges("what share of burst credits?", docs)
    assert {(e.new_doc, e.old_doc) for e in es} == {("b", "a"), ("c", "a")}
    assert POISON not in seen[0] and "what share of burst credits?" in seen[0]


def test_v3_three_values_is_not_a_supersession(monkeypatch):
    from moot.bench_erag import extract_v3
    reply = {"docs": [{"doc": i + 1, "value": v, "status": "current", "replaces": None, "date": f"2026-0{i + 1}-01"}
                      for i, v in enumerate(["10%", "20%", "30%"])]}
    monkeypatch.setattr(extract_v3, "ask", lambda prompt: reply)
    assert extract_v3.edges("q", {"a": "", "b": "", "c": ""}) == []


def test_v3_groq_sends_v3s_prompt_and_keeps_v3s_rules(monkeypatch, tmp_path):
    """v3-groq differs from v3 only in the model call: same prompt bytes, same pairing, and a cached reply skips the API."""
    from moot.bench_erag import extract_v3, extract_v3_groq as g
    reply = {"docs": [{"doc": 1, "value": "20%", "status": "superseded", "replaces": None, "date": "2026-03-11"},
                      {"doc": 2, "value": "30%", "status": "current", "replaces": "20%", "date": "2026-03-12"}]}
    docs = {"a": "burst credits were 20%", "b": "burst credits changed to 30%"}
    sent_v3, sent_g = [], []
    monkeypatch.setattr(extract_v3, "ask", lambda prompt: sent_v3.append(prompt) or reply)
    want = extract_v3.edges("what share of burst credits?", docs)
    monkeypatch.setattr(g, "CACHE", tmp_path)
    monkeypatch.setattr(g, "key", lambda: (_ for _ in ()).throw(AssertionError("cache hit must not call the API")))
    prompt = g.prompt_for("what share of burst credits?", docs)
    assert prompt == sent_v3[0]
    tmp_path.joinpath(g.cache_path(prompt).name).write_text(json.dumps(reply))
    got = g.edges("what share of burst credits?", docs)
    assert [(e.new_doc, e.old_doc, e.rule) for e in got] == [(e.new_doc, e.old_doc, e.rule) for e in want] == [("b", "a", "llm-replaces")]
    assert extract_v3.ask is not g.ask   # the swap is undone


def test_blind_ids_carry_no_gold_side_substring():
    """Every doc id a blind arm can see is a corpus doc id: no question id, no answer_ marker, and doc ids are opaque
    (dsid_ + 32 hex), so no id can smuggle a gold label. On the real data, also checks no blind id equals a question id."""
    import re
    from moot.bench_erag import DATA
    from moot.bench_erag.cut import VERSIONS
    pat = re.compile(r"dsid_[0-9a-f]{32}")
    cuts = [v[2] for v in VERSIONS.values() if v[2].exists()]
    if not cuts:
        pytest.skip("no blind cut on this machine (run make erag)")
    qids = set(json.loads((DATA / "pools.json").read_text()))
    for path in cuts:
        for qid, row in json.loads(path.read_text())["questions"].items():
            ids = row["baseline"] + row["moot"] + row["dropped"] + [p[k] for p in row["proof"] for k in ("old_doc", "new_doc")]
            for d in ids:
                assert pat.fullmatch(d), f"{path.name} {qid}: non-opaque id {d!r}"
                assert "answer_" not in d and "qst_" not in d and d not in qids
