"""Before and after reason extraction, on the four ingested GitHub repositories.

  python3 eval/eval_reasons.py            re-ingest each repo twice on the same day (titles only, then with stated reasons
                                          read from ADR text), audit both, write eval/results_reasons.{json,md}
  python3 eval/eval_reasons.py --cached   the same, reading stated reasons from data/github/*/reasons.json only

Needs network (git fetch, GitHub and OSV checks) and FalkorDB. Model calls happen only on a cache miss (local qwen3.8:27b
via Ollama by default; see moot/connectors/reasons.py). The final graph.json and summary.json are the "after" build.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from moot.connectors import github as gh  # noqa: E402
from moot.graph import graph  # noqa: E402
from moot import tools  # noqa: E402

REPOS = [r for r in os.getenv("MOOT_REASONS_REPOS", "").split(",") if r] or ["npryce/adr-tools", "thomvaill/log4brains", "alphagov/govuk-infrastructure", "alphagov/govuk-aws"]
VERDICTS = ("HOLDS", "MOOT", "DISPUTED", "UNDOCUMENTED", "RETIRED")
GATES = ("ALLOW", "REVALIDATE", "DENY")


def per_decision(full: str) -> dict[str, dict]:
    g = graph(gh.graph_name(full))
    s = json.loads((gh.load(full).parent / "summary.json").read_text())
    out = {}
    for r in tools.ledger(g, s["read_on"], 4):
        a = tools.audit_decision(g, r["id"], s["read_on"], 4)
        gate = tools.check_action(g, r["id"], s["read_on"])
        states = Counter(p["state"] for p in a.get("premises", []))
        stated = [p for p in a.get("premises", []) if p["id"].startswith("r_")]
        out[r["id"]] = dict(title=r["title"], verdict=r["verdict"], gate=gate["gate"], premises=dict(states),
                            stated=len(stated), stated_evidenced=sum(1 for p in stated if p["state"] not in ("unevidenced", "unchecked")),
                            reasons=[c["code"] for c in gate["reasons"]],
                            expired=[dict(premise=p["id"], text=p["text"], stated=p["id"].startswith("r_"), evidence=e["id"], at=e["at"], quote=e.get("quote") or "")
                                     for p in a.get("premises", []) if p["state"] == "expired"
                                     for e in [[x for x in p["evidence"] if x["rel"] == "CONTRADICTS"][-1]]])
    return out


def build(full: str, today: str, with_reasons: bool, call_model: bool) -> dict:
    gh.ingest(full, checks=True, today=today, reasons=with_reasons, call_model=call_model)
    s = gh.audit(full)
    return dict(summary=s, decisions=per_decision(full))


def counts(rows: dict, key: str, keys) -> dict:
    c = Counter(r[key] for r in rows.values())
    return {k: c.get(k, 0) for k in keys}


def holds_allow(rows: dict) -> int:
    return sum(1 for r in rows.values() if r["verdict"] == "HOLDS" and r["gate"] == "ALLOW")


def main() -> None:
    cached = "--cached" in sys.argv
    today = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--today=")), date.today().isoformat())
    result = dict(read_on=today, repos=[])
    for full in REPOS:
        print(f"{full}: before", flush=True)
        before = build(full, today, False, False)
        print(f"{full}: after", flush=True)
        after = build(full, today, True, not cached)
        b, a = before["decisions"], after["decisions"]
        st = after["summary"]["reasons"]
        holds = [r for r in a.values() if r["verdict"] == "HOLDS"]
        result["repos"].append(dict(
            repo=full, graph=gh.graph_name(full), decisions=len(a), model=st["model"],
            before=dict(verdicts=counts(b, "verdict", VERDICTS), gates=counts(b, "gate", GATES), holds_allow=holds_allow(b)),
            after=dict(verdicts=counts(a, "verdict", VERDICTS), gates=counts(a, "gate", GATES), holds_allow=holds_allow(a)),
            extraction=dict(adrs_read=st["extracted"], adrs_not_read=st["not_read"], reasons_kept=st["reasons"], reasons_dropped=st["dropped"],
                            tool_links=st["tool_links"], relations_kept=st["relations"], relations_dropped=st["relations_dropped"],
                            adrs_with_no_stated_reason=sum(1 for r in a.values() if not r["stated"] and r["verdict"] != "RETIRED")),
            holds_split=dict(checked=sum(1 for r in holds if r["gate"] == "ALLOW"), unevidenced=sum(1 for r in holds if r["gate"] != "ALLOW")),
            changed=[dict(id=k, title=a[k]["title"], before=b[k]["verdict"], after=a[k]["verdict"], gate_before=b[k]["gate"], gate_after=a[k]["gate"])
                     for k in sorted(a) if k in b and (b[k]["verdict"], b[k]["gate"]) != (a[k]["verdict"], a[k]["gate"])],
            per_decision=a))
    tot = lambda side, kind, k: sum(r[side][kind][k] for r in result["repos"])
    result["total"] = dict(decisions=sum(r["decisions"] for r in result["repos"]),
                           before=dict(verdicts={k: tot("before", "verdicts", k) for k in VERDICTS}, gates={k: tot("before", "gates", k) for k in GATES}),
                           after=dict(verdicts={k: tot("after", "verdicts", k) for k in VERDICTS}, gates={k: tot("after", "gates", k) for k in GATES}),
                           **{k: sum(r["extraction"][k] for r in result["repos"]) for k in result["repos"][0]["extraction"]},
                           holds_checked=sum(r["holds_split"]["checked"] for r in result["repos"]),
                           holds_unevidenced=sum(r["holds_split"]["unevidenced"] for r in result["repos"]))
    (ROOT / "eval" / "results_reasons.json").write_text(json.dumps(result, indent=1))
    (ROOT / "eval" / "results_reasons.md").write_text(markdown(result))
    print(markdown(result))


def markdown(R: dict) -> str:
    T = R["total"]
    vrow = lambda name, v: f"| {name} | " + " | ".join(str(v[k]) for k in VERDICTS) + " |"
    lines = [
        "# Stated reasons: before and after reading ADR text",
        "",
        f"Four public repositories ingested with `moot ingest-github`, each built twice on {R['read_on']}: first from titles, status lines "
        "and history alone (the connector before this change), then with the reasons each ADR states in its own Context, Decision and "
        "Consequences, read by a model and kept only as literal quoted spans (`moot/connectors/reasons.py`). Same day, same tool checks, "
        "same verdict rules. Model replies are cached in `data/github/<repo>/reasons.json`, so the after column re-derives without a model.",
        "",
        "## Verdicts",
        "",
        "| graph | " + " | ".join(VERDICTS) + " |",
        "|---|" + "---|" * len(VERDICTS),
    ]
    for r in R["repos"]:
        lines += [vrow(f"{r['repo']} before", r["before"]["verdicts"]), vrow(f"**{r['repo']} after**", r["after"]["verdicts"])]
    lines += [vrow("all four, before", T["before"]["verdicts"]), vrow("**all four, after**", T["after"]["verdicts"]), ""]
    lines += ["## What an agent may do (the gate, depth 6)", "", "| graph | " + " | ".join(GATES) + " |", "|---|" + "---|" * len(GATES)]
    for r in R["repos"]:
        for side in ("before", "after"):
            lines.append(f"| {r['repo']} {side} | " + " | ".join(str(r[side]["gates"][k]) for k in GATES) + " |")
    lines += [f"| **all four, after** | " + " | ".join(str(T["after"]["gates"][k]) for k in GATES) + " |", ""]
    lines += [
        "## What the model read and what the validator kept",
        "",
        f"- ADRs read: {T['adrs_read']} of {T['decisions']} decisions ({T['adrs_not_read']} not read). Reasons kept: {T['reasons_kept']}; "
        f"dropped by the validator: {T['reasons_dropped']} (quote not a literal span, in the title or Status, too short, a repeat, "
        "or a tool link that names no catalogue tool in its quote).",
        f"- Reasons linked to a checked tool (DERIVED_FROM its maintained / open source / no-known-vulnerability premises): {T['tool_links']}.",
        f"- Later ADRs judged against earlier reasons: {T['relations_kept']} dated SUPPORTS or CONTRADICTS edges kept, {T['relations_dropped']} dropped.",
        f"- Decisions still without a stated reason (not retired): {T['adrs_with_no_stated_reason']}.",
        "",
        "## Read this before the numbers",
        "",
        f"- **Most new HOLDS are not checked.** Of {T['after']['verdicts']['HOLDS']} HOLDS after extraction, {T['holds_checked']} pass the gate (ALLOW); "
        f"{T['holds_unevidenced']} rest on at least one stated reason nobody has evidence for either way, so the gate answers REVALIDATE. "
        "Moving a decision from UNDOCUMENTED to HOLDS means *the ADR says why, and nothing on record contradicts it*, not *we confirmed it*.",
        "- **The verdict rules did not change.** An unevidenced reason does not change a verdict (as in Larkspur); the change is that the "
        "graph now records what the ADR says, with the quote, character span, section, document and model on every Premise.",
        "- **A model can miss or misread a reason.** The span check stops invented quotes, not a wrong reading of a real one. Every reason "
        "in the graph links back to its sentence, so a reader can check it in one click.",
        "- **One local model, one run** (temperature 0, seed 7). A different model would keep different reasons.",
        "",
        "## Verdicts that changed",
        "",
        "| graph | decision | before | after | gate before | gate after |",
        "|---|---|---|---|---|---|",
    ]
    for r in R["repos"]:
        for c in r["changed"]:
            lines.append(f"| {r['graph']} | {c['id']}: {c['title'][:70]} | {c['before']} | {c['after']} | {c['gate_before']} | {c['gate_after']} |")
    lines += ["", "## Why each new MOOT is moot", "",
              "A decision turns MOOT only through a dated contradiction: a tool check (GitHub, OSV, licence) on a tool a stated reason "
              "depends on, or a later ADR's exact words. Check each one; this is where a misread reason would show.", "",
              "| graph | decision | reason | contradicted by | on | quote |", "|---|---|---|---|---|---|"]
    for r in R["repos"]:
        for c in r["changed"]:
            if c["after"] != "MOOT" or c["before"] == "MOOT":
                continue
            for x in r["per_decision"][c["id"]]["expired"]:
                q = x["quote"].replace("|", "/").replace("\n", " ")[:140]
                lines.append(f"| {r['graph']} | {c['id']} | {x['text'][:90]} | {x['evidence']} | {x['at']} | {q} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
