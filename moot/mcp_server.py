"""Moot as an MCP server: the same read-only tool catalogue, for any MCP client (Claude Desktop, Claude Code, Cursor).

Run: `moot mcp` (stdio). Every tool is a parameterised ro_query; the only write, record_finding, is
meant to be called after the human in the client approves.
"""
from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from . import agent, tools
from .graph import graph

INSTRUCTIONS = ("Audit a company's standing decisions against the dated evidence behind their premises. "
                "Verdicts come from FalkorDB path queries; cite evidence ids from the rows and say 'not in the graph' when a tool returns nothing.")
mcp = MCPServer("moot", instructions=INSTRUCTIONS)


def _g(name: str | None):
    """The tenant by default; any graph list_graphs names otherwise (the real ADRs, the backtest, an ingested repository)."""
    from .graph import BACKTEST_GRAPH, GH_PREFIX, PUBLIC_GRAPH, connect
    if name and name not in (graph().name, PUBLIC_GRAPH, BACKTEST_GRAPH) and not (name.startswith(GH_PREFIX) and name in connect().list_graphs()):
        raise ValueError(f"no graph named {name}; call list_graphs")
    return graph(name) if name else graph()


@mcp.tool()
def list_graphs() -> str:
    """Every graph Moot can audit: the demo company (default), the real public ADRs, the backtest, and each GitHub repository
    brought in with ingest_github. Pass a name as `graph` to the other tools."""
    from .api import graphs
    return json.dumps(graphs(), default=str)


@mcp.tool()
def find_decision(query: str, graph: str | None = None) -> str:
    """Resolve a question or phrase to candidate decisions using the graph's full-text index."""
    return json.dumps(tools.find_decision(_g(graph), query))


@mcp.tool()
def audit_decision(decision_id: str, as_of: str | None = None, depth: int = 4, graph: str | None = None) -> str:
    """Verdict for one decision (HOLDS, MOOT, DISPUTED, UNDOCUMENTED, RETIRED) with premises up to `depth` hops, dated evidence, the traversal paths and the owner."""
    return json.dumps(tools.audit_decision(_g(graph), decision_id, as_of, depth), default=str)


@mcp.tool()
def verdict_history(decision_id: str, as_of: str | None = None, graph: str | None = None) -> str:
    """Since when? Every verdict a decision has had and the date each began, re-audited on every date something in its graph happened."""
    return json.dumps(tools.verdict_history(_g(graph), decision_id, as_of), default=str)


@mcp.tool()
def who_knows_why(decision_id: str, as_of: str | None = None, graph: str | None = None) -> str:
    """Who knows why a decision was made: its owner, who wrote its record, who wrote evidence on its reasons; bus_factor is
    how many of them are still here. Read from authorship: knowing without writing it down does not count."""
    from . import people
    return json.dumps(people.knowers(_g(graph), decision_id, as_of), default=str)


@mcp.tool()
def departure_impact(person_id: str, as_of: str | None = None, graph: str | None = None) -> str:
    """What leaves with a person: live decisions nobody else still here knows the reasons for, reasons only they wrote
    evidence on, systems nobody else can explain, and who would inherit what they own. Computed on a copy of the graph."""
    from . import people
    return json.dumps(people.departure(_g(graph), person_id, as_of), default=str)


@mcp.tool()
def people_risk(as_of: str | None = None, graph: str | None = None) -> str:
    """Everyone still here ranked by the decisions only they know (bus factor 1) and by betweenness on the knowledge graph."""
    from . import people
    return json.dumps(people.people(_g(graph), as_of), default=str)


@mcp.tool()
def reason_single_points_of_failure(as_of: str | None = None, graph: str | None = None) -> str:
    """Reasons two or more live decisions rest on that only one document, or one person still here, vouches for."""
    from . import people
    return json.dumps(people.premise_spof(_g(graph), as_of), default=str)


@mcp.tool()
def ingest_github(repo: str, path: str | None = None) -> str:
    """Bring a public GitHub repository's ADR folder and its pull requests into a new graph (gh_<owner>_<repo>) and audit
    every decision. Writes a new graph and calls GitHub: call only after the user approves."""
    from .connectors import github as gh
    gh.ingest(repo, path)
    return json.dumps(gh.audit(repo), default=str)


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
def ledger(as_of: str | None = None, depth: int = 4, graph: str | None = None) -> str:
    """All decisions with verdicts, MOOT first."""
    return json.dumps(tools.ledger(_g(graph), as_of, depth))


@mcp.tool()
def ask(question: str, as_of: str | None = None, depth: int = 4) -> str:
    """Full audit from a natural-language question: resolve, audit, check memory, narrate with validated citations."""
    return json.dumps(agent.ask(graph(), question, as_of, depth), default=str)


@mcp.tool()
def record_finding(decision_id: str, verdict: str, as_of: str, depth: int = 4, cites: list[str] | None = None, note: str = "") -> str:
    """Write an approved verdict back to the graph as a Finding node. Call only after the user approves."""
    return json.dumps(tools.write_finding(graph(), decision_id, verdict, as_of, depth, cites or [], note))


@mcp.tool()
def check_action(decision_id: str, as_of: str | None = None, public_adrs: bool = False, graph: str | None = None) -> str:
    """Call before you enforce, rely on or renew a decision. Returns ALLOW, DENY or REVALIDATE with the graph path that
    justified it: DENY when a premise is contradicted or the decision is retired, REVALIDATE when the graph cannot vouch
    for it (no premise, disputed, unchecked, owner left). Only act on ALLOW. Read-only; always audits at full depth.
    Set public_adrs=true for the real public ADRs (ids like l4b-lunr, moj-004), or graph= any name list_graphs returns."""
    from .graph import PUBLIC_GRAPH
    return json.dumps(tools.check_action(_g(PUBLIC_GRAPH if public_adrs else graph), decision_id, as_of), default=str)


@mcp.tool()
def record_ruling(decision_id: str, premise_id: str, holds: bool, as_of: str, by: str | None = None, note: str = "") -> str:
    """Record an owner's ruling on a reason check_action could not vouch for (disputed, unchecked or unevidenced): holds=true
    if it still holds. Writes a dated edge the next audit cites, so the gate stops asking until newer evidence lands.
    Call only after the user approves."""
    return json.dumps(tools.write_ruling(graph(), decision_id, premise_id, holds, as_of, by, note), default=str)


@mcp.tool()
def evidence_packet(decision_id: str, as_of: str | None = None, markdown: bool = False, public_adrs: bool = False) -> str:
    """Everything behind one verdict, to hand to a reviewer: gate, reasons, receipts with quotes and dates, rulings,
    re-open memo, caveats, synthetic-data flag and snapshot digests. markdown=true returns it as a Markdown document."""
    from .graph import PUBLIC_GRAPH
    pk = tools.evidence_packet(graph(PUBLIC_GRAPH) if public_adrs else graph(), decision_id, as_of)
    if markdown and pk.get("found"):
        return tools.packet_markdown(pk)
    return json.dumps(pk, default=str)


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


# The public server (mounted at /mcp on the web app, streamable HTTP): read-only tools only. No finding, ruling, handover or
# ingest; `ask` is left out too, since it may call a model. Anyone can point an MCP client at https://<host>/mcp.
PUBLIC = ("list_graphs", "find_decision", "audit_decision", "verdict_history", "check_action", "ledger", "who_knows_why",
          "departure_impact", "people_risk", "reason_single_points_of_failure", "premise_impact", "trace_document",
          "decision_owner", "evidence_packet", "orphaned_decisions", "reopen_memo", "what_if", "riskiest_reasons", "real_world_ledger")


def public_server() -> MCPServer:
    pub = MCPServer("moot", instructions=INSTRUCTIONS + " This public server is read-only.")
    for name in PUBLIC:
        pub.tool()(globals()[name])
    return pub


def main():
    mcp.run()


if __name__ == "__main__":
    main()
