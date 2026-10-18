# Architecture and screens

## Architecture

```mermaid
flowchart LR
  subgraph Sources
    C[Larkspur corpus<br/>ADRs, PRs, tickets, chat, docs]
    CK[GitHub + OSV checks]
    GH[any GitHub repo<br/>ADR folder, git history, PRs]
  end
  GH -->|moot ingest-github| RS[reasons.py<br/>model proposes stated reasons;<br/>quote must be a literal span;<br/>cached in reasons.json]
  RS --> J
  C -->|extract: quotes must be substrings| J[graph.json]
  CK -->|dated Evidence| J
  J -->|MERGE, idempotent| F[(FalkorDB<br/>one named graph per company)]
  F -->|GRAPH.RO_QUERY<br/>fixed parameterised Cypher| T[tools.py]
  T --> V[verdict.py<br/>pure rules: verdict + agent gate]
  T --> PE[people.py<br/>KNOWS projection in a scratch graph:<br/>algo.WCC, algo.betweenness]
  V --> A[agent.py<br/>narrate, validate citations]
  A --> API[FastAPI + Next.js UI]
  A --> MCP[MCP server]
  A --> CLI[moot CLI]
  API -->|Approve click only| W[Finding / OWNS / ruling writes]
  W --> F
```

The four outcomes the organisers' reference architecture asks for: `answered_with_path`, `answered_from_memory`, `not_in_graph`, `unknown_entity`. Nothing is written to the graph without an approval call.

How a stated reason gets into the graph:

```mermaid
sequenceDiagram
  participant ADR as ADR text (git)
  participant M as model (local qwen3.8:27b)
  participant V as validator
  participant G as graph.json → FalkorDB
  ADR->>M: Context, Decision, Consequences + tools named
  M-->>V: reasons [{text, quote, tool}]
  V->>V: quote is a literal span? outside title/Status? tool named in the quote?
  V-->>G: Premise {text, quote, span, section, source, extracted_by} ←BECAUSE_OF─ Decision
  V-->>G: Premise ─DERIVED_FROM→ tool premises (GitHub / OSV checks)
  ADR->>M: each later ADR + earlier reasons sharing its words
  M-->>V: relations [{reason_id, rel, quote}]
  V-->>G: Evidence(later ADR) ─SUPPORTS/CONTRADICTS {at: its date, quote}→ Premise
```

## Screens

| | |
|---|---|
| ![The evidence path for D01: the decision, its stated reason, the expired reason two hops down, and PR-412 contradicting it](screens/evidence-path.png) **Evidence path.** Every verdict is drawn from the rows FalkorDB returned: D01, the reason, the expired reason behind it, PR-412. | ![The Cypher tab: the exact parameterised queries the answer ran, with rows and milliseconds](screens/cypher.png) **Cypher.** The exact read-only queries each answer ran, with parameters, row counts and milliseconds. |
| ![People: decisions only one person here can explain, bus factor, knowledge islands from algo.WCC, bridges from betweenness](screens/people.png) **People.** Who only knows what: bus factor, `algo.WCC` knowledge islands and betweenness on a KNOWS projection. | ![The Graph picker: Larkspur, 25 public ADRs, the backtest and each ingested GitHub repository](screens/graph-picker.png) **Graph picker.** One named graph per company: Larkspur, real ADRs, the backtest, every ingested repository. |
| ![log4brains: a stated reason, its exact quote from the ADR, and the later ADR that contradicts it](screens/stated-reason.png) **Stated reasons.** log4brains chose Lerna because "Yarn + Lerna seems to be a very good practice"; its own later ADR says Lerna "does not integrate well". The exact words, the source and the model that read them. | ![The landing page](screens/landing.png) **Landing.** Straight links to the evidence path, the Cypher, People and an audited repository. |

| | |
|---|---|
| ![Kubernetes as a company: the ledger of SIG Auth and SIG Node KEPs](screens/k8s-ledger.png) **Kubernetes.** The ledger of 158 KEPs, by verdict. | ![The judges' tour on the landing page](screens/judges.png) **Tour for judges.** The track, the video and seven places to check. |
