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


def main():
    mcp.run()


if __name__ == "__main__":
    main()
