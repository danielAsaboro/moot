"""`moot verify`: every headline number in README.md and eval/results*.md, checked against the output it came from.

The README quotes numbers from several eval files by hand. This catches drift before a reader does. Each claim is a
pattern in a document and the value the eval JSON says it should hold; a claim whose pattern is missing fails too, so a
reworded sentence cannot silently stop being checked. The backtest is re-scored offline from its committed snapshot and
must reproduce its results file byte for byte.

  moot verify            check the committed eval output against the documents
  moot verify --rerun    first re-run the deterministic evals from committed inputs into a scratch folder (needs
                         FalkorDB) and require their deterministic fields to equal the committed JSON

Exit status is non-zero on any mismatch.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from .stats import wilson

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "eval"
EVALS = {"results.json": "eval_retrieval.py", "results_scale.json": "eval_scale.py", "results_gate.json": "eval_gate.py",
         "results_ablation.json": "eval_ablation.py", "results_baseline.json": "eval_baseline.py"}
TIMING = {"seed_s", "audit", "ledger", "trace", "fresh_process", "samples"}  # measured, not derived: excluded from --rerun


def f2(x: float) -> str:
    return f"{x:.2f}"


def f1(x: float) -> str:
    return f"{x:.1f}"


def g(x: float) -> str:
    return f"{x:g}"


class Checker:
    def __init__(self):
        self.ok, self.bad = 0, []

    def expect(self, doc: str, text: str, label: str, pattern: str, expected: tuple) -> None:
        m = re.search(pattern, text)
        found = m.groups() if m else None
        exp = tuple(str(x) for x in expected)
        if found == exp:
            self.ok += 1
        else:
            self.bad.append(f"{doc}: {label}: expected {exp}, found {found if found else 'no match for the pattern'}")

    def equal(self, label: str, a, b) -> None:
        if a == b:
            self.ok += 1
        else:
            self.bad.append(f"{label}: differs")


def load(name: str, base: Path = EVAL):
    return json.loads((base / name).read_text())


def backtest_md() -> str | None:
    """Re-score the committed backtest snapshot offline into a scratch file and return the text."""
    if not (ROOT / "data" / "backtest" / "gates.json").exists():
        return None
    spec = importlib.util.spec_from_file_location("eval_backtest_verify", EVAL / "eval_backtest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with tempfile.TemporaryDirectory() as d:
        mod.OUT = Path(d) / "results_backtest.md"
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            mod.main()
        _BT["json"] = json.loads(mod.OUT.with_suffix(".json").read_text())
        return mod.OUT.read_text()


_BT: dict = {}


def check_history(c: Checker) -> None:
    """The real-history numbers the README and landing page promote (eval/results_backtest.json, re-scored offline)."""
    f = EVAL / "results_backtest.json"
    if not f.exists() or "json" not in _BT:
        return
    B = json.loads(f.read_text())
    c.equal("eval/results_backtest.json re-scored from data/backtest", B, _BT["json"])
    mongo = next(x for x in B["caught"] if "mongo" in x["id"].lower())
    es = next(x for x in B["caught"] if "elasticsearch" in x["id"].lower())
    c.expect("README.md", (ROOT / "README.md").read_text(), "real history sentence",
             r"Moot said DENY ([\d,]+) days before GOV\.UK replaced MongoDB.*?and ([\d,]+) days before GOV\.UK deprecated its Elasticsearch logging ADR; "
             r"median lead ([\d,]+) days\. It found (\d+) ADRs still marked accepted whose reasons died upstream",
             (f"{mongo['lead_days']:,}", f"{es['lead_days']:,}", f"{round(B['median_lead_days']):,}", B["flag_reading"]["real"]))


def check_headline(c: Checker, S: dict, G: dict, bt: str | None) -> None:
    """The results table at the top of the README."""
    doc, t = "README.md", (ROOT / "README.md").read_text()
    m = G["methods"]
    c.expect(doc, t, "headline gate", r"agent was allowed to act on \(of (\d+)\) \| \*\*(\d+)\*\* \| BM25 \+ change cues (\d+) · trust the ADR (\d+) \|",
             (G["n_block"], len(m["moot"]["false_allows"]), len(m["bm25"]["false_allows"]), len(m["adr"]["false_allows"])))
    p = G["public"]
    c.expect(doc, t, "headline public ADRs", r"denied with a dated reason \(of (\d+)\) \| \*\*(\d+)\*\* \| (\d+) of the \d+ still say",
             (p["records"], p["gates"].get("DENY", 0), p["accepted"]))
    big = max(S["scale"], key=lambda x: x["n"])
    c.expect(doc, t, "headline latency", r"Audit latency at ([\d,]+) noise documents, p50 \| \*\*([\d.]+) ms\*\*", (f"{big['n']:,}", f1(big["audit"]["p50"])))
    if bt is not None:
        caught, dd = re.search(r"\| \*\*Moot gate \(DENY\)\*\* \| \*\*(\d+) / (\d+)\*\*", bt).groups()
        rk = re.search(r"\| random, same number of flags \(mean of 200\) \| ([\d.]+) / ", bt).group(1)
        tk = re.search(r"\| trust the ADR \| (\d+) / ", bt).group(1)
        ak = re.search(r"\| age ≥ 3 years \| (\d+) / ", bt).group(1)
        c.expect(doc, t, "headline backtest", r"maintainers \(of (\d+) tool deaths\) \| \*\*(\d+)\*\* \| age ≥ 3 years (\d+) · random ([\d.]+) · trust the ADR (\d+) \|",
                 (dd, caught, ak, rk, tk))
        flags = re.search(r"\| \*\*Moot gate \(DENY\)\*\* \|.*?\| (\d+) of \d+ \|", bt).group(1)
        age_flags = re.search(r"\| age ≥ 3 years \|.*?\| (\d+) of \d+ \|", bt).group(1)
        real, false = re.search(r"\*\*(\d+)\*\* real, \*\*\d+\*\* right, \*\*(\d+)\*\* false alarm", bt).groups()
        c.expect(doc, t, "headline backtest flags", r"each with a dated reason \| \*\*(\d+)\*\* \((\d+) real, (\d+) false alarms\) \| age ≥ 3 years (\d+), none",
                 (flags, real, false, age_flags))
        c.expect(doc, t, "backtest precision sentence", r"the age rule catches (\d+) of the (\d+) deaths to Moot's (\d+).*?raises (\d+) flags.*?Moot raises (\d+), each.*?found (\d+) whose reason really died upstream and (\d+) false alarms",
                 (ak, dd, caught, age_flags, flags, real, false))


def check_baseline(c: Checker, B: dict) -> None:
    """Study S3: the README headline row and sentence, and the table in docs/evaluation.md."""
    a = B["arms"]
    t = (ROOT / "README.md").read_text()
    c.expect("README.md", t, "headline S3", r"dead decisions called HOLDS \(of (\d+)\) \| \*\*(\d+)\*\* \| RAG \+ same model (\d+) · RAG over stated reasons (\d+) \|",
             (a["moot"]["dead_n"], len(a["moot"]["dead_called_holds"]), len(a["rag_bm25"]["dead_called_holds"]), len(a["rag_premises"]["dead_called_holds"])))
    c.expect("README.md", t, "S3 sentence", r"Moot gets (\d+)/90 verdicts and (\d+)/(\d+) \"since when\" dates exactly; plain RAG with the same local model gets (\d+)/90 and (\d+)/(\d+)\. "
             r"The ablations say what carries it: ignoring dates drops Moot to (\d+)/90, removing FalkorDB \(same rules over retrieved documents\) to (\d+)/90, depth 1 to (\d+)/90",
             (a["moot"]["verdict"], a["moot"]["since"], a["moot"]["since_n"], a["rag_bm25"]["verdict"], a["rag_bm25"]["since"], a["rag_bm25"]["since_n"],
              a["moot_no_asof"]["verdict"], a["no_falkordb"]["verdict"], a["moot_depth1"]["verdict"]))
    ev = (ROOT / "docs" / "evaluation.md").read_text()
    for arm, label in (("rag_bm25", r"RAG: BM25 top-5 \+ model"), ("rag_premises", r"RAG over stated reasons \+ model \(FalkorDB removed\)"),
                       ("no_falkordb", r"ablation: FalkorDB removed, rules kept")):
        x = a[arm]
        c.expect("docs/evaluation.md", ev, f"S3 {arm}", rf"\| {label} \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|",
                 (x["verdict"], len(x["dead_called_holds"]), x["why"], x["since"], len(x["false_alarms"])))


def check_readme(c: Checker, R: dict, S: dict, G: dict, A: dict, bt: str | None) -> None:
    # the full tables live in docs/evaluation.md; the README keeps the headline table (check_headline)
    doc, t = "docs/evaluation.md", (ROOT / "docs" / "evaluation.md").read_text()
    # retrieval
    c.expect(doc, t, "retrieval n", r"for the (\d+) decisions that have an invalidating document", (R["n"],))
    c.expect(doc, t, "graph recall", r"\| graph path query \(Moot\) \| \*\*([\d.]+)\*\* \(consistency check, see below\) \| \*\*(\d+)%\*\* \|",
             (f2(R["graph_recall"]), round(R["graph_any"] * 100)))
    c.expect(doc, t, "BM25 recall", r"\| BM25 top-5, query = decision title \+ summary \| ([\d.]+) \| (\d+)% \|",
             (f2(R["bm25_recall"]), round(R["bm25_any"] * 100)))
    c.expect(doc, t, "random recall", r"\| random 5 docs \(control\) \| ([\d.]+) \|", (f2(R["random_recall"]),))
    # scale and latency
    for x in S["scale"]:
        a, l = x["audit"], x["ledger"]
        c.expect(doc, t, f"scale row {x['n']}", rf"\| {x['n']:,} \| (\d+) · ([\d.]+) / ([\d.]+) ms \| ([\d.]+) ms \| (\d+) · ([\d.]+) / ([\d.]+) ms \| ([\d.]+) s \|",
                 (a["n"], f1(a["p50"]), f1(a["p95"]), f1(a["cold"]), l["n"], f1(l["p50"]), f1(l["p95"]), f1(x["seed_s"])))
    v = S["verdicts"]
    c.expect(doc, t, "verdicts, graph", r"\| graph path rule \(Moot\) \| \*\*(\d+)/(\d+)\*\* \| \*\*([\d.]+)\*\* \| \*\*([\d.]+)\*\* \| \*\*([\d.]+)\*\* \|",
             (v["exact"], v["n"], *(f2(v["stale_graph"][k]) for k in ("precision", "recall", "f1"))))
    c.expect(doc, t, "verdicts, BM25", r"\| BM25 top-5 \+ change-cue heuristic \| – \| ([\d.]+) \| ([\d.]+) \| ([\d.]+) \|",
             tuple(f2(v["stale_bm25"][k]) for k in ("precision", "recall", "f1")))
    # gate
    m = G["methods"]
    nb, nh = G["n_block"], G["n_hold"]
    c.expect(doc, t, "gate, Moot", r"\| Moot gate \(full-depth audit \+ `gate\(\)`\) \| \*\*(\d+)\*\* \| ([\d.]+) \| \*\*(\d+)\*\* \| (\d+), all REVALIDATE \|",
             (len(m["moot"]["false_allows"]), f2(m["moot"]["false_allow_upper95"]), len(m["moot"]["stale_allowed"]), len(m["moot"]["false_blocks"])))
    for key, label in (("bm25", r"BM25 top-5 \+ change-cue heuristic"), ("adr", r"trust the ADR \(a doc-chat brain that finds it and stops\)")):
        c.expect(doc, t, f"gate, {key}", rf"\| {label} \| (\d+) \| ([\d.]+) \| (\d+) \| (\d+) \|",
                 (len(m[key]["false_allows"]), f2(m[key]["false_allow_upper95"]), len(m[key]["stale_allowed"]), len(m[key]["false_blocks"])))
    c.expect(doc, t, "gate denominators", r"An agent should act only on the (\d+) decisions that HOLD; the other (\d+) should be stopped", (nh, nb))
    c.expect(doc, t, "Wilson bound in prose", r"still allows a true rate up to (\d+)%", (round(m["moot"]["false_allow_upper95"] * 100),))
    p = G["public"]
    c.expect(doc, t, "public ADR gates", r"the gate denies (\d+) \(.*?\) and asks to revalidate (\d+) .*?; (\d+) of the (\d+) still say",
             (p["gates"].get("DENY", 0), p["gates"].get("REVALIDATE", 0), p["accepted"], p["records"]))
    # ablation
    dc = A["arms"]["delete_contradicts"]
    add = A["arms"]["add_contradicts"]
    c.expect(doc, t, "ablation, legacy", r"false allows, legacy rule \(no evidence = holds\) \| ([\d.]+) of (\d+) \| ([\d.]+) of (\d+) \|",
             (g(dc[0]["legacy"]["false_allows"]["mean"]), nb, g(dc[-1]["legacy"]["false_allows"]["mean"]), nb))
    c.expect(doc, t, "ablation, current", r"false allows, current gate \| ([\d.]+) of (\d+) \| ([\d.]+) of (\d+) \|",
             (g(dc[0]["current"]["false_allows"]["mean"]), nb, g(dc[-1]["current"]["false_allows"]["mean"]), nb))
    c.expect(doc, t, "ablation, junk", r"add (\d+) random CONTRADICTS edges: holds decisions denied \| ([\d.]+) of (\d+) \| ([\d.]+) of (\d+) \|",
             (add[-1]["added"], g(add[0]["current"]["holds_denied"]["mean"]), nh, g(add[-1]["current"]["holds_denied"]["mean"]), nh))
    # backtest, against the freshly re-scored results file
    if bt is None:
        return
    num = lambda pat: re.search(pat, bt).groups()
    in_force, dead = num(r"(\d+) decisions were in force at some point; \*\*(\d+)\*\* were later abandoned")
    tools_n, share, dead_tool, _ = num(r"(\d+) of them \((\d+)%\) pick an outside tool in their title\. .*?\*\*(\d+) of the (\d+)\*\*")
    c.expect(doc, t, "backtest coverage", r"(\d+) real decisions were in force at some point; (\d+) were later abandoned",
             (in_force, dead))
    c.expect(doc, t, "backtest tool share", r"Only (\d+) \((\d+)%\) pick an outside tool, and only \*\*(\d+) of the (\d+) deaths\*\*",
             (tools_n, share, dead_tool, dead))
    caught, dd, rec, lo, hi, missed, flagged = num(r"\| \*\*Moot gate \(DENY\)\*\* \| \*\*(\d+) / (\d+)\*\* \(recall ([\d.]+), ([\d.]+)–([\d.]+)\) \| (\d+) \| [^|]+ \| (\d+) of")
    wl, wh = wilson(int(caught), int(dd))
    c.expect(doc, t, "backtest Moot row", r"\| \*\*Moot gate\*\* \| \*\*(\d+) / (\d+)\*\* \(recall ([\d.]+), bootstrap 95% CI ([\d.]+)–([\d.]+), Wilson ([\d.]+)–([\d.]+)\) \| (\d+) \| (\d+) \|",
             (caught, dd, rec, lo, hi, f2(wl), f2(wh), missed, flagged))
    for label, pat in (("trust the ADR", r"trust the ADR"), ("age ≥ 3 years", r"age ≥ 3 years")):
        k, n2, ms_, fl = num(rf"\| {pat} \| (\d+) / (\d+) \| (\d+) \| [^|]+ \| (\d+) of")
        c.expect(doc, t, f"backtest {label}", rf"\| {pat} \| (\d+) / (\d+) \| (\d+) \| (\d+) \|", (k, n2, ms_, fl))
    rk, rn, rm, rf_ = num(r"\| random, same number of flags \(mean of 200\) \| ([\d.]+) / (\d+) \| ([\d.]+) \| – \| ([\d.]+) \|")
    c.expect(doc, t, "backtest random", r"\| random, same number of flags \| ([\d.]+) / (\d+) \| ([\d.]+) \| ([\d.]+) \|", (rk, rn, rm, rf_))


def check_results(c: Checker, R: dict, S: dict, G: dict) -> None:
    t = (EVAL / "results.md").read_text()
    c.expect("eval/results.md", t, "graph row", r"\| graph path query \(Moot\) \| \*\*([\d.]+)\*\* \| \*\*(\d+)%\*\* \|",
             (f2(R["graph_recall"]), round(R["graph_any"] * 100)))
    t = (EVAL / "results_gate.md").read_text()
    m = G["methods"]["moot"]
    c.expect("eval/results_gate.md", t, "Moot row", r"\| Moot gate \(depth 6\) \| \*\*(\d+)\*\* \| ([\d.]+) \| \*\*(\d+)\*\* \| \*\*(\d+)\*\* \|",
             (len(m["false_allows"]), f2(m["false_allow_upper95"]), len(m["stale_allowed"]), len(m["false_blocks"])))
    allow = sorted(k for k, r in G["moot"].items() if r["gate"] == "ALLOW")
    c.expect("eval/results_gate.md", t, "ALLOW list", r"- \*\*ALLOW\*\* \((\d+)\): ([^\n]*)", (len(allow), ", ".join(f"{k} (every premise has dated support)" for k in allow)))
    t = (EVAL / "results_scale.md").read_text()
    for x in S["scale"]:
        c.expect("eval/results_scale.md", t, f"recall row {x['n']}", rf"\| {x['n']:,} \| [\d,]+ \| [\d,]+ / [\d,]+ \| [\d.]+ \| \*\*([\d.]+)\*\* \| ([\d.]+) \|",
                 (f2(x["graph"]), f2(x["bm25"])))
    erag = EVAL / "results_erag.md"
    det = ROOT / "evidence" / "erag_deterministic.json"
    if erag.exists() and det.exists():
        d = json.loads(det.read_text())
        c.expect("eval/results_erag.md", erag.read_text(), "headline",
                 r"Moot blind (\d+)/(\d+) · ORACLE \(Canon's setup\) (\d+)/\d+ · BM25 baseline (\d+)/\d+",
                 (d["moot"]["retired_gold_in_context"], d["moot"]["counts"]["conflicts"] if "counts" in d["moot"] else d["counts"]["conflicts"],
                  d["oracle"]["retired_gold_in_context"], d["baseline"]["retired_gold_in_context"]))
        c.expect("README.md", (ROOT / "README.md").read_text(), "headline EnterpriseRAG-Bench",
                 r"still in the model's context \(of (\d+), lower is better\) \| \*\*(\d+)\*\* \| BM25 (\d+): a tie",
                 (d["counts"]["conflicts"] if "counts" in d else d["moot"]["counts"]["conflicts"], d["moot"]["retired_gold_in_context"], d["baseline"]["retired_gold_in_context"]))


def check_reasons(c: Checker) -> None:
    """Stated reasons (eval/results_reasons.json): the README sentence, each repo's committed summary, and the charts."""
    f = EVAL / "results_reasons.json"
    if not f.exists():
        return
    R = json.loads(f.read_text())
    T = R["total"]
    t = (ROOT / "README.md").read_text()
    c.expect("README.md", t, "reasons sentence",
             r"UNDOCUMENTED fell from (\d+) to (\d+) of (\d+) decisions\. Of the (\d+) HOLDS after, (\d+) pass the gate",
             (T["before"]["verdicts"]["UNDOCUMENTED"], T["after"]["verdicts"]["UNDOCUMENTED"], T["decisions"],
              T["after"]["verdicts"]["HOLDS"], T["holds_checked"]))
    ev = (ROOT / "docs" / "evaluation.md").read_text()
    for side, label in (("before", r"before \(titles, status lines, history\)"), ("after", r"after \(plus (\d+) quoted reasons, (\d+) tool links, (\d+) later-ADR edges\)")):
        v = T[side]["verdicts"]
        extra = (T["reasons_kept"], T["tool_links"], T["relations_kept"]) if side == "after" else ()
        c.expect("docs/evaluation.md", ev, f"reasons table, {side}", rf"\| {label} \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|",
                 (*extra, v["HOLDS"], sum(r[side]["holds_allow"] for r in R["repos"]), v["MOOT"], v["UNDOCUMENTED"], v["RETIRED"]))
    for r in R["repos"]:
        sf = ROOT / "data" / "github" / r["repo"].replace("/", "__") / "summary.json"
        if sf.exists():
            got = json.loads(sf.read_text()).get("verdicts", {})
            c.equal(f"{r['repo']} summary.json verdicts = results_reasons after", {k: v for k, v in r["after"]["verdicts"].items() if v},
                    {k: v for k, v in got.items() if v})
    sys.path.insert(0, str(EVAL))
    import charts  # eval/charts.py
    for name, svg in charts.charts().items():
        out = ROOT / "docs" / "charts" / name
        c.equal(f"docs/charts/{name} drawn from the result files", out.read_text() if out.exists() else None, svg)


def check_router(c: Checker) -> None:
    """The router eval (eval/results_router.json): the README sentence and the summary table in the results file."""
    f = EVAL / "results_router.json"
    if not f.exists():
        return
    S = json.loads(f.read_text())["summary"]
    m = S["misrouted"]
    c.expect("README.md", (ROOT / "README.md").read_text(), "router sentence",
             r"On (\d+) ordinary questions the keyword rules misroute it routes (\d+) correctly", (m["n"], m["model"]))
    t = (EVAL / "results_router.md").read_text()
    for name, s in (("rules misroute them", m), ("rules already route them", S["control"])):
        c.expect("eval/results_router.md", t, f"router row, {name}", rf"\| {name} \| (\d+) \| (\d+)/\d+ .*?\| \*\*(\d+)/\d+\*\*",
                 (s["n"], s["rules"], s["model"]))


def check_test_count(c: Checker) -> None:
    """The README's test count is the number pytest collects."""
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=ROOT, capture_output=True, text=True).stdout
    m = re.search(r"(\d+) tests? collected", out)
    if m:
        c.expect("README.md", (ROOT / "README.md").read_text(), "test count", r"`make demo`\), (\d+) tests,", (m.group(1),))


def strip_timing(x):
    if isinstance(x, dict):
        return {k: strip_timing(v) for k, v in x.items() if k not in TIMING}
    if isinstance(x, list):
        return [strip_timing(v) for v in x]
    return x


def rerun_evals(c: Checker) -> None:
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, MOOT_EVAL_OUT=d)
        for out, script in EVALS.items():
            print(f"re-running eval/{script} ...", flush=True)
            subprocess.run([sys.executable, str(EVAL / script)], cwd=ROOT, env=env, check=True, capture_output=True)
            c.equal(f"eval/{out} (deterministic fields) re-derived from committed inputs", strip_timing(load(out)), strip_timing(load(out, Path(d))))


def main(rerun: bool = False) -> int:
    c = Checker()
    if rerun:
        rerun_evals(c)
    R, S, G, A, B = (load(n) for n in EVALS)
    bt = backtest_md()
    if bt is not None:
        c.equal("eval/results_backtest.md re-scored from data/backtest", bt, (EVAL / "results_backtest.md").read_text())
    check_headline(c, S, G, bt)
    check_baseline(c, B)
    check_readme(c, R, S, G, A, bt)
    check_results(c, R, S, G)
    check_reasons(c)
    check_router(c)
    check_history(c)
    check_test_count(c)
    for b in c.bad:
        print("MISMATCH", b)
    print(f"moot verify: {c.ok} checks passed, {len(c.bad)} failed")
    return 1 if c.bad else 0


if __name__ == "__main__":
    sys.exit(main(rerun="--rerun" in sys.argv))
