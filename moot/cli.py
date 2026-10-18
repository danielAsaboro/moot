"""moot: seed | stats | ask | audit | ledger | packet | verify | serve | mcp | generate | extract | eval"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv=None):
    p = argparse.ArgumentParser(prog="moot")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate", help="render the synthetic corpus and truth.json from the spec")
    sub.add_parser("build", help="build data/graph.json from data/truth.json")
    s = sub.add_parser("seed", help="MERGE data/graph.json into FalkorDB (idempotent), plus the public-ADR graph"); s.add_argument("--file"); s.add_argument("--graph", help="named graph (default: the tenant)"); s.add_argument("--fresh", action="store_true", help="drop the graph first")
    sub.add_parser("stats")
    a = sub.add_parser("ask"); a.add_argument("question"); a.add_argument("--as-of"); a.add_argument("--depth", type=int, default=4)
    b = sub.add_parser("audit"); b.add_argument("decision_id"); b.add_argument("--as-of"); b.add_argument("--depth", type=int, default=4)
    k = sub.add_parser("packet", help="the evidence packet behind one verdict (Markdown or JSON)"); k.add_argument("decision_id"); k.add_argument("--as-of"); k.add_argument("--json", action="store_true")
    vf = sub.add_parser("verify", help="check every headline number in README.md and eval/results*.md against the eval JSON; non-zero on drift")
    vf.add_argument("--rerun", action="store_true", help="first re-run the deterministic evals from committed inputs (needs FalkorDB)")
    dp = sub.add_parser("departure", help="what leaves with a person (computed on a copy of the graph)"); dp.add_argument("person_id"); dp.add_argument("--as-of"); dp.add_argument("--graph")
    pp = sub.add_parser("people", help="who only knows what: bus factor and betweenness per person"); pp.add_argument("--as-of"); pp.add_argument("--graph")
    ot = sub.add_parser("teams", help="hidden teams: communities of collaborators against the official teams"); ot.add_argument("--graph")
    cp = sub.add_parser("connect", help="who connects two people: the shortest chain of shared records"); cp.add_argument("a"); cp.add_argument("b"); cp.add_argument("--graph")
    l = sub.add_parser("ledger"); l.add_argument("--as-of"); l.add_argument("--depth", type=int, default=4); l.add_argument("--graph")
    v = sub.add_parser("serve"); v.add_argument("--port", type=int, default=None)
    sub.add_parser("mcp", help="run the read-only MCP server on stdio")
    sub.add_parser("realworld", help="check real public ADRs against GitHub and OSV -> data/realworld/ (network)")
    ig = sub.add_parser("ingest-github", help="a public repo's ADR folder + PRs -> graph gh_<owner>_<repo>, audited (network)")
    ig.add_argument("repo", help="owner/name"); ig.add_argument("--path", help="the ADR folder, if not found automatically"); ig.add_argument("--no-checks", action="store_true", help="skip the GitHub/OSV tool checks")
    ig.add_argument("--no-reasons", action="store_true", help="do not read stated reasons from ADR text")
    ig.add_argument("--cached", action="store_true", help="read stated reasons from data/github/<repo>/reasons.json only, never a model")
    gp = sub.add_parser("gate-paths", help="gate every decision that governs these files (.moot/paths.json); exit 1 on a DENY")
    gp.add_argument("files", nargs="+")
    dr = sub.add_parser("draft-pr", help="draft the pull request that re-opens a MOOT decision in an ingested repository (nothing is pushed)")
    dr.add_argument("repo"); dr.add_argument("decision_id"); dr.add_argument("--as-of")
    sub.add_parser("hook", help="Claude Code PreToolUse hook: block an edit to a file governed by a dead decision (reads stdin)")
    ik = sub.add_parser("ingest-keps", help="Kubernetes Enhancement Proposals of some SIGs -> graph gh_kubernetes_enhancements, audited (network)")
    ik.add_argument("--sig", action="append", help="a SIG folder under keps/ (repeatable; default sig-auth)")
    ik.add_argument("--cached", action="store_true", help="read stated reasons from data/github/kubernetes__enhancements/reasons.json only")
    e = sub.add_parser("extract", help="LLM extraction from data/corpus into data/extracted.json"); e.add_argument("--limit", type=int)
    args = p.parse_args(argv)

    if args.cmd == "generate":
        from .corpus.generate import main as gen; gen(); return
    if args.cmd == "build":
        from .ingest.build_graph import main as build; build(); return
    if args.cmd == "verify":
        from .verify import main as verify; return verify(rerun=args.rerun)
    if args.cmd == "realworld":
        from .realworld.check import main as rw; rw(); return
    if args.cmd == "gate-paths":
        from .hook import gate_paths_cli
        raise SystemExit(gate_paths_cli(args.files))
    if args.cmd == "draft-pr":
        from .draftpr import draft
        print(json.dumps(draft(args.repo, args.decision_id, args.as_of), indent=1)); return
    if args.cmd == "hook":
        from .hook import hook_cli
        raise SystemExit(hook_cli())
    if args.cmd == "ingest-keps":
        from .connectors import keps
        keps.ingest(args.sig, call_model=not args.cached)
        s = keps.audit()
        print(f"{s['repo']}: {s['decisions']} KEPs from {s['folder']} ({s['people']} people) -> graph {s['graph']}; verdicts {s['verdicts']}")
        return
    if args.cmd == "ingest-github":
        from .connectors import github as gh
        s = gh.ingest(args.repo, args.path, checks=not args.no_checks, reasons=not args.no_reasons, call_model=not args.cached)
        s = gh.audit(args.repo)
        print(f"{s['repo']}: {s['decisions']} decisions from {s['folder']} ({s['pull_requests']} pull requests, {s['people']} people) -> graph {s['graph']}")
        if s.get("reasons"):
            r = s["reasons"]
            print(f"stated reasons: {r['reasons']} kept from {r['extracted']} ADRs ({r['dropped']} dropped by the validator, {r['not_read']} not read), "
                  f"{r['tool_links']} linked to tool checks, {r['relations']} dated SUPPORTS/CONTRADICTS from later ADRs; model {r['model']}")
        print("verdicts:", ", ".join(f"{k} {v}" for k, v in s["verdicts"].items()), "· gate:", ", ".join(f"{k} {v}" for k, v in s["gates"].items()))
        for m in s["moot"]:
            print(f"  MOOT  {m['id']}  {m['title']}")
        print(f"open it: moot ledger --graph {s['graph']}  or  /app/?graph={s['graph']}")
        return
    from .graph import graph, seed, stats
    if args.cmd == "seed":
        from pathlib import Path
        from .graph import DATA, PUBLIC_GRAPH
        out = seed(graph(args.graph), Path(args.file) if args.file else None, fresh=args.fresh)
        if not args.file and not args.graph:  # the real-data graphs ship as snapshots too
            from .connectors import github as gh
            from .graph import BACKTEST_GRAPH
            extra = {PUBLIC_GRAPH: DATA / "realworld" / "graph.json", BACKTEST_GRAPH: DATA / "backtest" / "graph.json"}
            extra.update({gh.graph_name(r): gh.load(r) for r in gh.ingested()})
            for name, f in extra.items():
                if f.exists():
                    out[name] = seed(graph(name), f, fresh=args.fresh)
        print(json.dumps(out, indent=1)); return
    if args.cmd == "stats":
        print(json.dumps(stats(graph()), indent=1)); return
    from . import tools, agent
    if args.cmd == "ask":
        r = agent.ask(graph(), args.question, args.as_of, args.depth)
        print(f"[{r['outcome']}] " + r["answer"])
        if r.get("audit"):
            for pr in r["audit"]["premises"]:
                print("  path:", " -> ".join(n["id"] for n in pr["path"]), f"[{pr['state']}]")
        return
    if args.cmd == "audit":
        print(json.dumps(tools.audit_decision(graph(), args.decision_id, args.as_of, args.depth), indent=1)); return
    if args.cmd == "packet":
        pk = tools.evidence_packet(graph(), args.decision_id, args.as_of)
        if not pk["found"]:
            print(f"{args.decision_id} is not in the graph"); return 1
        print(json.dumps(pk, indent=1, default=str) if args.json else tools.packet_markdown(pk)); return
    if args.cmd == "departure":
        from . import people
        r = people.departure(graph(args.graph), args.person_id, args.as_of)
        if not r["found"]:
            print(f"{args.person_id} is not in the graph"); return 1
        print(f"If {r['person']['name']} left on {r['as_of']}:")
        print(f"  decisions nobody else here knows the reasons for: {len(r['leaves'])}")
        for d in r["leaves"]:
            print(f"    {d['verdict']:<12} {d['id']}  {d['title']}")
        for x in r["only_they_evidence"]:
            print(f"  only they wrote evidence on: {x['id']} \"{x['text']}\" ({', '.join(x['evidence'])})")
        if r["systems_nobody_else_explains"]:
            print("  systems nobody else can explain:", ", ".join(r["systems_nobody_else_explains"]))
        if r["owned"]:
            print(f"  owns {len(r['owned'])} live decisions; next up the reporting line: {r['successor']['name'] if r['successor'] else 'nobody'}")
        return
    if args.cmd == "teams":
        from . import org
        r = org.hidden_teams(graph(args.graph))
        for c in r["communities"]:
            print(f"{'HIDDEN ' if c['hidden'] else ''}{c['size']:>3} people, {c['main_share']:.0%} {c['main_team']}  hub {c['hub']}  {c['teams']}")
        print("bridges: " + ", ".join(f"{b['name']} ({b['betweenness']:g})" for b in r["bridges"][:5]))
        return
    if args.cmd == "connect":
        from . import org
        r = org.connection(graph(args.graph), args.a, args.b)
        print(" → ".join(r["people"]) if r["found"] else r["why"])
        for st in r.get("steps", []):
            print(f"  {st['frm']} – {st['to']}: {', '.join(st['records'])}")
        return
    if args.cmd == "people":
        from . import people
        r = people.people(graph(args.graph), args.as_of)
        for p in r["people"]:
            print(f"{p['name'] or p['id']:<24} only knows {len(p['sole']):>2}  knows {p['knows']:>2}  betweenness {p['betweenness']:>7}  {', '.join(p['sole'])}")
        print(f"bus factor 0: {', '.join(r['bus_factor']['zero']) or 'none'} · bus factor 1: {len(r['bus_factor']['one'])} decisions")
        return
    if args.cmd == "ledger":
        for r in tools.ledger(graph(args.graph), args.as_of, args.depth):
            print(f"{r['verdict']:<13} {r['id']}  {r['title']}  (owner: {r['owner']}{'' if r['owner_active'] else ', left'})")
        return
    if args.cmd == "serve":
        import os, uvicorn
        uvicorn.run("moot.api:app", host="0.0.0.0", port=args.port or int(os.getenv("PORT", "8000")))
        return
    if args.cmd == "mcp":
        from .mcp_server import main as mcp_main; mcp_main(); return
    if args.cmd == "extract":
        from .ingest.extract import main as ex; ex(limit=args.limit); return


if __name__ == "__main__":
    sys.exit(main())
