"""Backtest score: did Moot's gate stop real decisions before their own maintainers abandoned them?

Reads data/backtest/{decisions,gates,evidence,code}.json (written by `make backtest`) and writes
eval/results_backtest.md. No network, no model, no FalkorDB needed to re-score.

Unit: one decision (an ADR whose title picks an outside tool), followed month by month while it is in force.
  caught       the gate said DENY on or before the date the repository abandoned the decision
  missed       the repository abandoned it and the gate never said DENY before that
  flagged      the gate said DENY while the repository still marks the decision as in force (not necessarily wrong:
               see the reading below; the answer key only knows what maintainers wrote down)
Baselines get the same months: trust the ADR (never flags), an age rule (flag at 3 years), and a random flagger
that flags as many decisions as Moot does, each at a random month while it is in force.
"""
from __future__ import annotations

import json
import random
import statistics
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BT = ROOT / "data" / "backtest"
OUT = ROOT / "eval" / "results_backtest.md"
END = "2026-10-17"
B = 2000  # bootstrap resamples

# Our reading of each decision Moot flagged while its repository still lists it as in force, and of each miss.
# This is the one place our judgement enters, so it is kept apart from the answer key and every line says why.
READING = {
    "CMSgov/easi-app:0002-use-terraform.md": "real: the team still runs Terraform; nothing in the repo revisits the 2023 license change",
    "alphagov/govuk-aws:0012-security-groups-in-terraform.md": "real: same Terraform license premise",
    "ministryofjustice/modernisation-platform:0035-terraform-workspaces.md": "real: decided 16 months after the license change without mentioning it",
    "edgexfoundry/edgex-docs:0017-consul-security.md": "real: same license change, for Consul",
    "CMSgov/easi-app:0014-use-mux-for-routing.md": "real: gorilla/mux was archived in Dec 2022, revived in 2023, and has gone quiet again",
    "CMSgov/easi-app:0017-go-orm.md": "real: the upstream repository has gone quiet",
    "CMSgov/easi-app:0036-rich-text-editor.md": "real: upstream went quiet within months of the decision",
    "GSA/notifications-api:0009-adr-implement-backstopjs-to-improve-qa.md": "real: upstream went quiet a year after the decision",
    "alphagov/govuk-aws:0007-puppet-cert-management.md": "real: no public Puppet commits since Perforce said new builds would be private (Nov 2024); govuk-aws is itself a legacy repo",
    "alphagov/govuk-aws:0008-postgres-on-puppetmaster.md": "real: same Puppet premise",
    "alphagov/govuk-aws:0025-use-elasticache-for-redis.md": "false alarm: a managed AWS service is not bound by Redis's license (AWS answered with the Valkey fork)",
    "alphagov/govuk-aws:0029-combine-api-redis-into-backend-redis.md": "false alarm: same managed-Redis premise",
    "ministryofjustice/cloud-platform:001-Use-AWS-hosted-elasticsearch.md": "right: a managed service, but the platform has since moved its logging to OpenSearch (ADR-017) without retiring this ADR",
    "ministryofjustice/cloud-platform:016-Kibana-is-open-to-all-service-teams.md": "right: same move to OpenSearch",
    "alphagov/govuk-infrastructure:0013-expose-external-metrics-for-hpa.md": "real: the upstream repository has gone quiet",
    "kyma-project/community:dr-006-Kubeless_as_the_Faas_solution.md": "right: Kubeless is archived (its repo now lives under vmware-archive); the DR was never retired",
    "mozilla/fxa:0021-use-internjs-testing.md": "right: FxA chose Playwright over Intern in ADR 0028 (2021), Intern has since left its manifests, and this ADR was never retired",
    "openedx/edx-platform:0003-permissions-via-bridgekeeper.rst": "real: the upstream repository has gone quiet",
    "openedx/edx-platform:permissions.rst": "mixed: ADR 0003 chose bridgekeeper over django-rules two months later and never retired this ADR, yet `rules` is still pinned in requirements/edx/base.txt",
    "thomvaill/log4brains:20200925-use-prettier-eslint-airbnb-for-the-code-style.md": "real: the upstream repository has gone quiet",
    "thomvaill/log4brains:20201103-use-lunr-for-search.md": "real: Lunr.js has gone quiet",
    "wmde/fundraising-application:006_Vue.js.md": "real: a 2019 Vue decision is a Vue 2 decision, and Vue 2 reached end of life on 2023-12-31; the frontend has since moved to its own repository, so this one's manifests cannot say whether it migrated",
}
MISSES = {
    "CMSgov/easi-app:0005-frontend-toolchain-choice.md": "outside, unread: Meta stopped recommending Create React App (react.dev, 2023) while its repo still had commits",
    "openedx/paragon:0005-usage-of-reactstrap.rst": "internal: developer ergonomics, two months after the decision",
    "kyma-project/community:dr-008-Dex_as_an_OIDC_authenticator.md": "internal: an architecture change (DR 021 removed the API proxies)",
    "operate-first/blueprint:0018-migration-to-keycloak.md": "internal: the Operate First project wound down; three ADRs deprecated the same day",
}


def days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def add_years(d: str, n: int) -> str:
    x = date.fromisoformat(d)
    try:
        return x.replace(year=x.year + n).isoformat()
    except ValueError:
        return x.replace(year=x.year + n, day=28).isoformat()


def end_of(d: dict) -> str:
    return min(x for x in (d["death"]["date"] if d["death"] else None, d["deleted"], END) if x)


def outcome(d: dict, flag: str | None) -> str:
    if d["death"]:
        return "caught" if flag and flag <= d["death"]["date"] else "missed"
    return "flagged" if flag and flag <= end_of(d) else "quiet"


def score(decisions: list[dict], flags: dict[str, str | None]) -> dict:
    o = [outcome(d, flags[d["id"]]) for d in decisions]
    caught, missed, flagged = o.count("caught"), o.count("missed"), o.count("flagged")
    leads = [days(flags[d["id"]], d["death"]["date"]) for d, x in zip(decisions, o) if x == "caught"]
    return dict(caught=caught, missed=missed, flagged=flagged, quiet=o.count("quiet"), dead=caught + missed, alive=flagged + o.count("quiet"),
                recall=caught / (caught + missed) if caught + missed else 0.0,
                confirmed=caught / (caught + flagged) if caught + flagged else 0.0, leads=leads)


def boot(decisions, flags, key, seed=7):
    rng = random.Random(seed)
    vals = []
    for _ in range(B):
        s = [rng.choice(decisions) for _ in decisions]
        vals.append(score(s, flags)[key])
    vals.sort()
    return vals[int(0.025 * B)], vals[int(0.975 * B) - 1]


def main() -> None:
    every = json.loads((BT / "decisions.json").read_text())
    gates = json.loads((BT / "gates.json").read_text())
    ev = json.loads((BT / "evidence.json").read_text())
    code = json.loads((BT / "code.json").read_text()) if (BT / "code.json").exists() else {}
    tool_dec = [d for d in every if d["tools"]]
    by_id = {d["id"]: d for d in tool_dec}

    moot = {i: next((x["as_of"] for x in s if x["gate"] == "DENY"), None) for i, s in gates.items()}
    trust = {i: None for i in gates}
    age = {i: (add_years(by_id[i]["born"], 3) if add_years(by_id[i]["born"], 3) <= end_of(by_id[i]) else None) for i in gates}
    months_total = sum(len(s) for s in gates.values())
    budget = sum(1 for f in moot.values() if f)  # random flagger: the same number of decisions as Moot, each at a random in-force month
    rand_runs = []
    for k in range(200):
        rng = random.Random(1000 + k)
        pick = set(rng.sample(sorted(gates), budget))
        f = {i: (rng.choice(s)["as_of"] if i in pick else None) for i, s in gates.items()}
        rand_runs.append(score(tool_dec, f))

    S = {"Moot gate (DENY)": score(tool_dec, moot), "trust the ADR": score(tool_dec, trust), "age ≥ 3 years": score(tool_dec, age)}
    R = {k: statistics.mean(r[k] for r in rand_runs) for k in ("caught", "missed", "flagged", "recall", "confirmed")}

    dead_all = [d for d in every if d["death"]]
    repos = sorted({d["repo"] for d in every})
    L = []
    w = L.append
    w("# Backtest: real decisions, judged by their own maintainers\n")
    w(f"Generated by `make backtest` (re-score offline with `python3 eval/eval_backtest.py`). Histories read on {END}.\n")
    w("**The question.** Rewind a real repository to any past month, show Moot only what existed then, and ask its agent gate whether an agent may act on each decision. "
      "Did it say DENY before the repository's own maintainers abandoned the decision?\n")
    w("**The answer key, written by neither of us.** The git history of the ADR folders of "
      f"{len(repos)} public repositories. A decision dies on the commit where its own repository marked it superseded, deprecated or invalidated, "
      "moved it to an archive folder, or titled a later ADR as dropping the tool it picked. The key never enters the graph: Moot sees no retirement edges, "
      "only dated evidence about the tools.\n")
    w("## Coverage first\n")
    w(f"- {len(every)} decisions were in force at some point; **{len(dead_all)}** were later abandoned by their own repository "
      f"({sum(1 for d in every if d['born_dead'])} more arrived already dead, with no date, and are left out).")
    w(f"- {len(tool_dec)} of them ({len(tool_dec) / len(every):.0%}) pick an outside tool in their title. Only those can be checked from outside, "
      f"and only **{sum(1 for d in tool_dec if d['death'])} of the {len(dead_all)}** deaths fall among them.")
    w(f"- So outside evidence can speak to at most {sum(1 for d in tool_dec if d['death']) / len(dead_all):.0%} of the decisions real teams abandon. "
      "The rest die for internal reasons, which is what the Larkspur company graph (tickets, chat, PRs) is for.\n")
    w("## Score on the decisions that pick a tool\n")
    w(f"{len(tool_dec)} decisions, {months_total:,} decision-months, each gate call a dated path query against the FalkorDB graph `backtest`. "
      "Intervals are 95% bootstrap over decisions.\n")
    w("| method | caught before maintainers | missed | median lead | flagged while still listed in force | share of flags later confirmed |")
    w("|---|---|---|---|---|---|")
    for name, s in S.items():
        lead = f"{statistics.median(s['leads'])} days" if s["leads"] else "–"
        if name.startswith("Moot"):
            lo, hi = boot(tool_dec, moot, "recall")
            clo, chi = boot(tool_dec, moot, "confirmed")
            w(f"| **{name}** | **{s['caught']} / {s['dead']}** (recall {s['recall']:.2f}, {lo:.2f}–{hi:.2f}) | {s['missed']} | {lead} | "
              f"{s['flagged']} of {s['alive']} | {s['confirmed']:.2f} ({clo:.2f}–{chi:.2f}) |")
        else:
            w(f"| {name} | {s['caught']} / {s['dead']} | {s['missed']} | {lead} | {s['flagged']} of {s['alive']} | {s['confirmed']:.2f} |")
    w(f"| random, same number of flags (mean of 200) | {R['caught']:.1f} / {S['trust the ADR']['dead']} | {R['missed']:.1f} | – | {R['flagged']:.1f} | {R['confirmed']:.2f} |")
    w("")
    tally = {}
    for d in tool_dec:
        if not d["death"] and moot[d["id"]] and moot[d["id"]] <= end_of(d):
            k = READING.get(d["id"], "unread").split(":")[0]
            tally[k] = tally.get(k, 0) + 1
    w("**Read it plainly.** Six deaths is too few to rank methods on recall: the intervals overlap, and Moot catches about what a random flagger "
      "with the same budget would. The key was fixed before the gate ran. What separates the methods is the flags on decisions still listed as in force, "
      f"which the key cannot grade. The age rule raises {S['age ≥ 3 years']['flagged']} of them with no reason attached. Moot raises {S['Moot gate (DENY)']['flagged']}, "
      "each naming a dated fact a reviewer can check in a minute, and reading them one by one (below) gives: "
      + ", ".join(f"**{v}** {k}" for k, v in sorted(tally.items(), key=lambda kv: -kv[1])) + ". "
      "*Right* means the repository itself later moved off the tool in another document without retiring the ADR; *mixed* means it said so but the code disagrees; "
      "*real* means the premise did die upstream and the repository has not said what it will do about it.\n")

    w("## Every death, and what Moot said before it\n")
    w("| decision | decided | abandoned by its repo | how | Moot | why |")
    w("|---|---|---|---|---|---|")
    for d in sorted([d for d in tool_dec if d["death"]], key=lambda d: d["death"]["date"]):
        f = moot[d["id"]]
        res = (f"DENY from {f} ({days(f, d['death']['date'])} days early)" if f and f <= d["death"]["date"] else "never denied")
        why = next((x["reasons"][0] for x in gates[d["id"]] if x["gate"] == "DENY"), MISSES.get(d["id"], ""))
        w(f"| [{d['title']}]({d['url']}) ({d['repo']}) | {d['born']} | {d['death']['date']} | {d['death']['kind']}: “{d['death']['quote'][:70]}” | {res} | {why} |")
    w("")
    w("## Every flag on a decision its repository still lists as in force\n")
    w("The answer key cannot grade these: an ADR left at *accepted* may be current, or simply never revisited. "
      "Our reading of each is below (the only judgement in this file); *still in the code* is the repository's own dependency manifests at HEAD, where the tool has one.\n")
    w("| decision | Moot DENY from | dated reason | still in the code | our reading |")
    w("|---|---|---|---|---|")
    for d in sorted(tool_dec, key=lambda d: (moot[d["id"]] or "9")):
        if d["death"] or not moot[d["id"]] or moot[d["id"]] > end_of(d):
            continue
        reason = next(x["reasons"][0] for x in gates[d["id"]] if x["gate"] == "DENY")
        inc = [v for k, v in code.items() if k.startswith(d["id"] + "|")]
        inc_s = ("yes" if any(v["at_head"] for v in inc) else "no" if any(v["at_decision"] for v in inc) else "not visible") if inc else "n/a"
        w(f"| [{d['title']}]({d['url']}) ({d['repo']}) | {moot[d['id']]} | {reason} | {inc_s} | {READING.get(d['id'], '')} |")
    w("")
    w("## What the evidence is, and what is left out\n")
    w(f"- **Maintained**: the default branch of each tool's own repository, cloned from GitHub ({len(ev)} tools). "
      "A gap of 365 days without a commit CONTRADICTS “<tool> is actively maintained” on the day the gap reaches 365 days; "
      "the next commit SUPPORTS it again, which the gate reads as REVALIDATE. The same 365-day rule as the live checker (`moot realworld`).")
    w("- **Open source**: the vendors' own license announcements, dated (`moot/backtest/tools.py`, LICENSE_EVENTS).")
    w("- **Left out**: the live checker's vulnerability premise. OSV dates when an advisory was published, but not which release a team was on at a past date, "
      "so it cannot be replayed without guessing.")
    w("- **Limits**: tools are matched on ADR titles only (bodies name the tools they rejected too); "
      "ADRs that were imported in bulk use the date written in the ADR, or are left out when they arrived already dead; "
      "“not abandoned” means only that nobody wrote it down.")
    OUT.write_text("\n".join(L) + "\n")
    # the headline numbers the landing page and README quote, read by /api/evals and checked by `moot verify`
    caught = [dict(id=d["id"], title=d["title"], repo=d["repo"], url=d["url"], denied_from=moot[d["id"]], abandoned=d["death"]["date"],
                   lead_days=days(moot[d["id"]], d["death"]["date"]), how=d["death"]["quote"][:120],
                   why=next(x["reasons"][0] for x in gates[d["id"]] if x["gate"] == "DENY"))
              for d in sorted(tool_dec, key=lambda d: d["death"]["date"] if d["death"] else "") if d["death"] and outcome(d, moot[d["id"]]) == "caught"]
    OUT.with_suffix(".json").write_text(json.dumps(dict(
        end=END, repos=len(repos), decisions=len(every), tool_decisions=len(tool_dec), deaths=len(dead_all),
        tool_deaths=sum(1 for d in tool_dec if d["death"]), caught=caught,
        median_lead_days=statistics.median(S["Moot gate (DENY)"]["leads"]) if S["Moot gate (DENY)"]["leads"] else None,
        methods={k: {x: v[x] for x in ("caught", "missed", "flagged", "alive", "dead")} for k, v in S.items()},
        random=dict(caught=round(R["caught"], 1), flagged=round(R["flagged"], 1)), flag_reading=tally), indent=1) + "\n")
    print(OUT.read_text())


if __name__ == "__main__":
    main()
