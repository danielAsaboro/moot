"""Gate eval: how often would each method let an agent act on a decision it should not?

The gate's job is to block. Ground truth (Larkspur, 30 decisions, as of the spec date): an agent may act on a decision
only when its expected verdict is HOLDS. Everything else (MOOT, DISPUTED, UNDOCUMENTED, RETIRED) should be stopped.

  moot gate        tools.check_action: the audit at depth 6, then the pure gate rule
  moot, depth 1    the same rule on a depth-1 audit (what a gate that only reads the ADR's stated reasons would do)
  bm25 + cues      allow unless a later BM25 top-5 document carries a change cue (the retrieval-only heuristic of eval_scale)
  trust the ADR    allow every accepted ADR (a doc-chat brain that finds the ADR and stops)

Reported: false allows (a stale, retired or undocumented decision let through) and false blocks (a decision that holds,
stopped). Then the same gate over the 25 real public ADRs, where there is no answer key: it reports what it stopped and why.
No model is involved. Writes eval/results_gate.md and the raw rows to eval/results_gate.json (read by `moot verify`).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from moot import tools  # noqa: E402
from moot.graph import DATA, connect, seed  # noqa: E402
from moot.stats import wilson_upper  # noqa: E402
from moot.verdict import gate  # noqa: E402
from eval_scale import baseline_stale  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.getenv("MOOT_EVAL_OUT") or ROOT / "eval")  # `moot verify --rerun` writes elsewhere and compares
truth = json.loads((DATA / "truth.json").read_text())


def main() -> None:
    db = connect()
    g = db.select_graph("moot_eval_gate")
    seed(g, None, fresh=True)
    as_of = truth["as_of"]
    gold = {d["id"]: d["expected"] for d in truth["decisions"]}
    stale = baseline_stale(truth["evidence"])
    allowed = {
        "moot": {k: tools.check_action(g, k, as_of)["allowed"] for k in gold},
        "depth1": {k: gate(tools.audit_decision(g, k, as_of, 1))["allowed"] for k in gold},
        "bm25": {k: not stale[k] for k in gold},
        "adr": {k: True for k in gold},
    }
    moot_rows = {k: tools.check_action(g, k, as_of) for k in gold}
    # decisions a depth-1 audit calls HOLDS although they should be stopped, and what the depth-1 gate still caught them on
    shallow = {k: gate(tools.audit_decision(g, k, as_of, 1)) for k in gold
               if tools.audit_decision(g, k, as_of, 1)["verdict"] == "HOLDS" and gold[k] != "HOLDS"}
    g.delete()

    def score(a: dict[str, bool]) -> dict:
        fa = sorted(k for k in gold if a[k] and gold[k] != "HOLDS")
        fb = sorted(k for k in gold if not a[k] and gold[k] == "HOLDS")
        return dict(fa=fa, fb=fb, fa_stale=[k for k in fa if gold[k] in ("MOOT", "DISPUTED")])

    s = {m: score(a) for m, a in allowed.items()}
    n_block = sum(1 for v in gold.values() if v != "HOLDS")
    n_stale = sum(1 for v in gold.values() if v in ("MOOT", "DISPUTED"))
    n_hold = len(gold) - n_block
    label = {"moot": "Moot gate (depth 6)", "depth1": "same rule, depth 1", "bm25": "BM25 top-5 + change cues", "adr": "trust the ADR"}
    out = ["# Gate eval: would an agent be allowed to act on a dead decision?", "",
           f"Larkspur, as of {as_of}: {len(gold)} decisions. An agent should act only on the {n_hold} that HOLD; "
           f"the other {n_block} ({n_stale} MOOT or DISPUTED, the rest UNDOCUMENTED or RETIRED) should be stopped.", "",
           f"| method | false allows (of {n_block}) | 95% upper bound on false-allow rate | of which stale (of {n_stale}) | false blocks (of {n_hold}) | let through |",
           "|---|---|---|---|---|---|"]
    for m in ("moot", "depth1", "bm25", "adr"):
        x = s[m]
        b = "**" if m == "moot" else ""
        out.append(f"| {label[m]} | {b}{len(x['fa'])}{b} | {wilson_upper(len(x['fa']), n_block):.2f} | {b}{len(x['fa_stale'])}{b} | "
                   f"{b}{len(x['fb'])}{b} | {', '.join(x['fa']) or '–'} |")
    fb_codes = {k: sorted({r["code"] for r in moot_rows[k]["reasons"]}) for k in s["moot"]["fb"]}
    out += ["", f"The upper bound is the one-sided 95% Wilson bound: {len(s['moot']['fa'])} false allows in {n_block} still leaves room for a "
            f"true rate up to {wilson_upper(len(s['moot']['fa']), n_block):.0%}. Thirty decisions cannot show a gate is safe, only that it is not "
            "obviously unsafe."]
    if fb_codes:
        lead = (f"**The Moot gate's {len(fb_codes)} false blocks are all REVALIDATE, never DENY**"
                if all(moot_rows[k]["gate"] == "REVALIDATE" for k in fb_codes) else f"**The Moot gate's {len(fb_codes)} false blocks**")
        out += ["", lead + ": " + ", ".join(f"{k} ({'+'.join(c)})" for k, c in fb_codes.items()) + ". Each rests on a premise with no dated evidence "
                "either way. The spec calls these decisions HOLDS because nothing contradicts them; the gate refuses to let an agent act on "
                "that, because nothing ever checked them either. An owner's ruling (`POST /api/ruling`) is a dated edge that settles it. "
                "Until 2026-10-18 the gate printed \"all premises hold\" for them and scored 0 false blocks; that result is withdrawn "
                "([docs/studies.md](../docs/studies.md)). The depth-1 row has no false blocks for the same reason it would miss a dead "
                "reason two hops down: it never looks at the unchecked premises below the stated one."]
    out += ["", "How the Moot gate decided:", ""]
    by = {}
    for k, r in moot_rows.items():
        by.setdefault(r["gate"], []).append(k)
    for gname in ("ALLOW", "DENY", "REVALIDATE"):
        ids = sorted(by.get(gname, []))
        out.append(f"- **{gname}** ({len(ids)}): " + ", ".join(f"{k} ({'+'.join(sorted({r['code'] for r in moot_rows[k]['reasons']})) or 'every premise has dated support'})" for k in ids))
    if shallow:
        caught = {k: sorted({r["code"] for r in x["reasons"]}) for k, x in shallow.items()}
        out += ["", f"Depth matters, but this corpus hides it: at depth 1, {', '.join(sorted(shallow))} audit as HOLDS, because the reason that died "
                "is two hops below the one the ADR states. The depth-1 gate still stops them, but only on "
                + "; ".join(f"{k}: {', '.join(c) or 'nothing'}" for k, c in sorted(caught.items()))
                + ", not on the dead reason. Those are reasons to ask, not a reason to stop: the depth-1 gate answers REVALIDATE where the "
                "full-depth gate answers DENY and names the contradicting evidence. The gate always audits at depth 6.", ""]

    # real public ADRs: no answer key, so report what the gate stopped and on what evidence
    snap = json.loads((DATA / "realworld" / "checks.json").read_text())
    pg = db.select_graph("moot_eval_gate_public")
    seed(pg, DATA / "realworld" / "graph.json", fresh=True)
    on = snap["summary"]["checked_on"]
    rw = {r["id"]: tools.check_action(pg, r["id"], on) for r in snap["records"]}
    pg.delete()
    counts = {}
    for r in rw.values():
        counts[r["gate"]] = counts.get(r["gate"], 0) + 1
    accepted = sum(1 for r in snap["records"] if not r.get("status"))
    out += ["## Real public ADRs", "",
            f"{len(rw)} records from {snap['summary']['repos']} repositories, checked {on}. {accepted} of them still say *accepted*, "
            "so an agent that trusts the ADR would act on all of those.", "",
            "| gate | records | why |", "|---|---|---|"]
    for gname in ("DENY", "REVALIDATE", "ALLOW"):
        ids = sorted(k for k, r in rw.items() if r["gate"] == gname)
        why = "; ".join(f"{k}: {rw[k]['reasons'][0]['text']}" for k in ids) if gname != "ALLOW" else "every checked reason holds"
        out.append(f"| {gname} | {len(ids)} | {why} |")
    out += ["", "## Threats to validity, worst first", "",
            "1. **Common-mode answer key.** The Larkspur answer key comes from the same spec as the graph, so the Moot row says the gate rule "
            "and the verdict rule agree, not that extraction is solved. The graph ablation ([results_ablation.md](results_ablation.md)) shows "
            "which edges the answers depend on.",
            f"2. **Small n.** {n_block} decisions to stop and {n_hold} to allow; one decision moves a rate by 5–10 points. Read the bounds, not the zeros.",
            "3. **Baselines without a model.** BM25 + cues and trust-the-ADR get no model, by design, so this file reproduces offline. A "
            "model-judged RAG baseline is in `eval/eval_e2e.py` and has not been run (no key on the build machine).",
            "4. **Real ADRs have no answer key.** The second table reports what the gate did and on what evidence, not whether it was right.",
            "", "REVALIDATE is not a verdict on the decision; it means the graph cannot vouch for it, which is exactly when an agent should stop."]
    (OUT / "results_gate.md").write_text("\n".join(out) + "\n")
    raw = dict(as_of=as_of, n=len(gold), n_block=n_block, n_stale=n_stale, n_hold=n_hold,
               methods={m: dict(false_allows=x["fa"], stale_allowed=x["fa_stale"], false_blocks=x["fb"],
                                false_allow_upper95=round(wilson_upper(len(x["fa"]), n_block), 4)) for m, x in s.items()},
               moot={k: dict(gate=r["gate"], reasons=sorted({c["code"] for c in r["reasons"]}), digest=r["snapshot"]["digest"]) for k, r in moot_rows.items()},
               public=dict(checked_on=on, records=len(rw), accepted=accepted, gates=counts,
                           by_record={k: r["gate"] for k, r in rw.items()}))
    (OUT / "results_gate.json").write_text(json.dumps(raw, indent=1, sort_keys=True) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
