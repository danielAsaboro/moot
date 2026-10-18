# Moot over MCP

`moot mcp` runs the same read-only tool catalogue the web app uses as an MCP server on stdio. Every tool is a fixed,
parameterised `GRAPH.RO_QUERY`; the model in your client never writes Cypher. The writes (`record_finding`,
`record_ruling`, `record_handover`) are meant to be called only after the person in the client approves.

## Setup

Install and seed once (FalkorDB embedded through `falkordblite`, or point `FALKORDB_HOST`/`FALKORDB_PORT` at your own):

```bash
pip install -e ".[dev]"
make db && make seed
```

**Claude Code**

```bash
claude mcp add moot -- python3 -m moot.cli mcp
```

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`) or **Cursor** (`.cursor/mcp.json`):

```json
{"mcpServers": {"moot": {"command": "python3", "args": ["-m", "moot.cli", "mcp"], "cwd": "/path/to/moot"}}}
```

Use the Python that has Moot installed (for example `/path/to/moot/.venv/bin/python`) if `python3` on your PATH does not.

## The one call an agent should make first

`check_action(decision_id, as_of?, graph?)` answers **ALLOW**, **DENY** or **REVALIDATE** before an agent enforces, relies
on or renews a decision, with the evidence id and path for every reason. Only act on ALLOW. It audits at depth 6 and never
writes. Example: `check_action("D01")` is DENY, because PR-412 contradicted the reason two hops down on 2026-03-02.

## Tools

| tool | what it answers |
|---|---|
| `list_graphs` | every graph Moot can audit: Larkspur (default), `public_adrs`, `backtest`, each `gh_<owner>_<repo>` |
| `find_decision` | full-text search for a decision by words in its title or summary |
| `audit_decision` | the verdict with premises to `depth` hops, dated evidence, traversal paths and the owner |
| `check_action` | the agent gate: ALLOW / DENY / REVALIDATE, with reasons and a digest of the rows it read |
| `verdict_history` | since when: every verdict the decision has had, re-audited on each date something changed |
| `ledger` | every decision with its verdict, MOOT first |
| `who_knows_why` | the people who own it, wrote its record, or wrote evidence on a reason below it; bus factor |
| `departure_impact` | what leaves with a person (WCC on a KNOWS projection in a scratch graph) |
| `people_risk` | bus factor and betweenness per person |
| `reason_single_points_of_failure` | reasons that two or more live decisions rest on, vouched for by one document or person |
| `premise_impact` | blast radius of a reason: every decision resting on it, plus PageRank |
| `trace_document` | what a new document can reach (`algo.SPpaths`) |
| `what_if` / `riskiest_reasons` | if this reason broke today, what falls; the reasons with the widest blast radius |
| `decision_owner` / `orphaned_decisions` | the owner of record on a date; decisions whose owner left, with a successor from `REPORTS_TO` |
| `reopen_memo` / `evidence_packet` | the re-open memo for a moot decision; the evidence packet behind a verdict, as Markdown |
| `real_world_ledger` | the 25 public ADRs checked against GitHub and OSV |
| `ingest_github` | read a public repository's ADR folder, history and PRs into a new graph (network; stated reasons read by the local model when it is running, else from the cache) |
| `ask` | a question in words, routed to one of the tools above, narrated with validated citations |
| `record_finding` / `record_ruling` / `record_handover` | the approval-gated writes |

`find_decision`, `audit_decision`, `verdict_history`, `check_action`, `ledger`, `who_knows_why`, `departure_impact`, `people_risk` and `reason_single_points_of_failure` take `graph=` to read a graph other than the default; the others read the default graph (`check_action` and `evidence_packet` also take `public_adrs=true`).
