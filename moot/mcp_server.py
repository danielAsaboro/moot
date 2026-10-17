"""Moot as an MCP server: the same read-only tool catalogue, for any MCP client (Claude Desktop, Claude Code, Cursor).

Run: `moot mcp` (stdio). Every tool is a parameterised ro_query; the only write, record_finding, is
meant to be called after the human in the client approves.
"""
from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from . import agent, tools
from .graph import graph

mcp = MCPServer("moot", instructions="Audit a company's standing decisions against the dated evidence behind their premises. "
              "Verdicts come from FalkorDB path queries; cite evidence ids from the rows and say 'not in the graph' when a tool returns nothing.")


@mcp.tool()
def find_decision(query: str) -> str:
    """Resolve a question or phrase to candidate decisions using the graph's full-text index."""
    return json.dumps(tools.find_decision(graph(), query))


@mcp.tool()
def audit_decision(decision_id: str, as_of: str | None = None, depth: int = 4) -> str:
    """Verdict for one decision (HOLDS, MOOT, DISPUTED, UNDOCUMENTED, RETIRED) with premises up to `depth` hops, dated evidence, the traversal paths and the owner."""
    return json.dumps(tools.audit_decision(graph(), decision_id, as_of, depth), default=str)


@mcp.tool()
def premise_impact(premise_id: str) -> str:
    """Every decision and system that rests on a premise, with its PageRank in the dependency graph."""
    return json.dumps(tools.premise_impact(graph(), premise_id))


@mcp.tool()
def trace_document(evidence_id: str) -> str:
    """Shortest paths from a document (PR, ticket, chat, doc) to every decision it can affect."""
    return json.dumps(tools.trace_document(graph(), evidence_id))


@mcp.tool()
def decision_owner(decision_id: str, as_of: str | None = None) -> str:
    """Who owns a decision as of a date, and whether they are still active."""
    return json.dumps(tools.decision_owner(graph(), decision_id, as_of))


@mcp.tool()
def ledger(as_of: str | None = None, depth: int = 4) -> str:
    """All decisions with verdicts, MOOT first."""
    return json.dumps(tools.ledger(graph(), as_of, depth))


@mcp.tool()
def ask(question: str, as_of: str | None = None, depth: int = 4) -> str:
    """Full audit from a natural-language question: resolve, audit, check memory, narrate with validated citations."""
    return json.dumps(agent.ask(graph(), question, as_of, depth), default=str)


@mcp.tool()
def record_finding(decision_id: str, verdict: str, as_of: str, depth: int = 4, cites: list[str] | None = None, note: str = "") -> str:
    """Write an approved verdict back to the graph as a Finding node. Call only after the user approves."""
    return json.dumps(tools.write_finding(graph(), decision_id, verdict, as_of, depth, cites or [], note))


@mcp.tool()
def orphaned_decisions(as_of: str | None = None) -> str:
    """Live decisions whose owner has left, grouped by who left, each with its reasons, verdict and the suggested new owner (first active person up the reporting line)."""
    return json.dumps(tools.orphans(graph(), as_of), default=str)


@mcp.tool()
def record_handover(decision_id: str, to_person_id: str, as_of: str) -> str:
    """Hand a decision to a new owner from a date (new OWNS edge). Call only after the user approves."""
    return json.dumps(tools.handover(graph(), decision_id, to_person_id, as_of))


@mcp.tool()
def reopen_memo(decision_id: str, as_of: str | None = None, depth: int = 4) -> str:
    """Draft a re-open memo: which reason broke, the dated evidence, other decisions on the same reason, and the suggested owner."""
    return json.dumps(tools.reopen_memo(graph(), decision_id, as_of, depth), default=str)


@mcp.tool()
def what_if(reason: str, as_of: str | None = None, depth: int = 4) -> str:
    """Pretend a reason broke today. `reason` is a premise id (p_...) or words to match one. Returns every decision that would fall and the chain to it."""
    g = graph()
    pid = reason if reason.startswith("p_") else next((c["id"] for c in tools.find_premise(g, reason)), None)
    if not pid:
        return json.dumps(dict(found=False, answer="No reason in the graph matches that."))
    return json.dumps(tools.what_if(g, pid, as_of, depth), default=str)


@mcp.tool()
def riskiest_reasons(as_of: str | None = None, limit: int = 10) -> str:
    """Reasons ranked by how many standing decisions rest on them, directly or through derived premises."""
    return json.dumps(tools.riskiest_reasons(graph(), as_of, 4, limit), default=str)


@mcp.tool()
def real_world_ledger() -> str:
    """Real public ADRs (ministryofjustice, alphagov, log4brains, backstage) with verdicts on their unwritten reasons: is the chosen tool still maintained, open source, free of known vulnerabilities."""
    from .graph import PUBLIC_GRAPH
    import json as _j
    from .graph import DATA
    as_of = _j.loads((DATA / "realworld" / "checks.json").read_text())["summary"]["checked_on"]
    return json.dumps(tools.ledger(graph(PUBLIC_GRAPH), as_of, 2), default=str)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
