"""moot: seed | stats | ask | audit | ledger | serve | mcp | generate | extract | eval"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv=None):
    p = argparse.ArgumentParser(prog="moot")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate", help="render the synthetic corpus and truth.json from the spec")
    sub.add_parser("build", help="build data/graph.json from data/truth.json")
    s = sub.add_parser("seed", help="MERGE data/graph.json into FalkorDB (idempotent)"); s.add_argument("--file"); s.add_argument("--fresh", action="store_true", help="drop the graph first")
    sub.add_parser("stats")
    a = sub.add_parser("ask"); a.add_argument("question"); a.add_argument("--as-of"); a.add_argument("--depth", type=int, default=4)
    b = sub.add_parser("audit"); b.add_argument("decision_id"); b.add_argument("--as-of"); b.add_argument("--depth", type=int, default=4)
    l = sub.add_parser("ledger"); l.add_argument("--as-of"); l.add_argument("--depth", type=int, default=4)
    v = sub.add_parser("serve"); v.add_argument("--port", type=int, default=None)
    sub.add_parser("mcp", help="run the read-only MCP server on stdio")
    e = sub.add_parser("extract", help="LLM extraction from data/corpus into data/extracted.json"); e.add_argument("--limit", type=int)
    args = p.parse_args(argv)

    if args.cmd == "generate":
        from .corpus.generate import main as gen; gen(); return
    if args.cmd == "build":
        from .ingest.build_graph import main as build; build(); return
    from .graph import graph, seed, stats
    if args.cmd == "seed":
        from pathlib import Path
        print(json.dumps(seed(graph(), Path(args.file) if args.file else None, fresh=args.fresh), indent=1)); return
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
    if args.cmd == "ledger":
        for r in tools.ledger(graph(), args.as_of, args.depth):
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
