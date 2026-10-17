# Moot
One line: a company brain that audits the reasons behind your standing decisions and tells you which ones have expired, with the evidence path.
For / Job / Done: engineering lead inheriting a team's rules / "which decisions still hold, which have an expired reason, where is the proof?" / a ledger of verdicts, each with the traversal path, citations and an approval-gated re-open memo; orphaned decisions routed to a successor; what-if and riskiest reasons.
Sponsor mechanism (critical path): FalkorDB named graph per tenant; verdicts are `ro_query` path queries over Decision → Premise ← Evidence with validity windows; PageRank/SPpaths/WCC as tools; Findings written back as nodes.
Features in scope (5): graph + seven read-only tools (incl. timeline) · corpus + idempotent ingest · audit agent with validated narration · evals vs BM25 and random, noise scaling, verdict accuracy · web UI with rot chart, depth toggle, graph and Cypher views, approval gate · upgrades: orphaned-decision handover (REPORTS_TO walk), re-open memo + Approve, what-if + riskiest reasons · real-world proof: 25 public ADRs in graph public_adrs (moot/realworld, GitHub + OSV checks, snapshot in data/realworld).
Not building: live Slack/Jira connectors, auth, graph editing in the UI, embeddings.
Stack: Python 3.11+, falkordb client, FastAPI, vanilla JS, anthropic SDK (narration only), mcp.
Run: `make db && make seed && make serve` · Test: `make test` · Eval: `make eval` · Deploy: Dockerfile + docker-compose (FalkorDB sidecar).
Repo map: moot/ (graph.py seed, tools.py queries, verdict.py pure logic, agent.py narration, api.py, mcp_server.py, corpus/ spec+generator, ingest/ build_graph+extract) · web/ UI · data/ corpus, truth.json, graph.json · eval/ · docs/falkordb.md.
Invariants (never): never let the model write Cypher · never let the model touch the database · never write to the graph without an approval call · never cite an id the rows did not return · never change a verdict without a dated edge.
Design: follow design.md.
Rules that disqualify: FalkorDB must be load-bearing (it is: verdicts are path queries); README must carry the graph model and the Cypher; AI use must be disclosed.
Evidence rules: a claim is done only with a row in the private hackathon/evidence.md; mocks are never evidence.
Forbidden artifacts: plans, research and the tracker live in the private parent folder, never here.
