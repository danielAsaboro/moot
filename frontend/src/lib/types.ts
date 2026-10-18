// Response shapes of the FastAPI routes (moot/api.py). Written from real responses; see frontend/fixtures/*.json.

export type Verdict = "HOLDS" | "MOOT" | "DISPUTED" | "UNDOCUMENTED" | "RETIRED" | "NOT_YET" | "NOT_IN_GRAPH";
export type GateDecision = "ALLOW" | "DENY" | "REVALIDATE";
export type PremiseState = "holds" | "expired" | "disputed" | "unchecked" | "unevidenced";
export type Rel = "SUPPORTS" | "CONTRADICTS";

export interface PathNode { id: string; label: string; title: string }

export interface Query { cypher: string; params: Record<string, unknown>; rows: number; ms: number; write: boolean }

export interface DecisionNode { id: string; title: string; summary: string; decided_on: string; source?: string; label?: string }

export interface EvidenceEvent {
  id: string; title: string; kind: string; date: string; rel: Rel; at: string;
  quote?: string; author?: string | null; stated?: string; ruling?: boolean;
}

export interface Premise {
  id: string; text: string; kind?: string; hops: number; path: PathNode[]; state: PremiseState;
  unchecked?: string | null; evidence: EvidenceEvent[]; contradicted_before_decision?: boolean;
  /** a reason read from the ADR's own words: the exact span, its section, the document and the model that read it */
  quote?: string; section?: string; source?: string; extracted_by?: string;
}

export interface Owner {
  id: string; name: string; role?: string; valid_from?: string; valid_to?: string | null; active: boolean;
  handed_over_from?: string | null;
}

export interface SupersededBy { id: string; title: string; at: string; kind: "decision" | "document"; quote?: string }

export interface Audit {
  found: boolean; decision: DecisionNode; as_of: string; depth: number; verdict: Verdict; premises: Premise[];
  superseded_by: SupersededBy | null; source?: { id: string; title: string; date: string; excerpt?: string; kind?: string; path?: string } | null;
  systems: string[]; owner: Owner | null;
  /** The team that answers for it on as_of, and who leads that team then (Team / LEADS) */
  team?: { id: string; name: string; source?: string; projects: number;
           leads: { id: string; name: string; role: string; from: string; to: string }[];
           former: { id: string; name: string; role: string; from: string; to: string }[] } | null;
}

export interface Impact {
  found: boolean; premise: { id: string; text: string; kind?: string }; derived_from: { id: string; text: string } | null;
  pagerank: number | null; decisions: { id: string; title: string; hops: number; systems: string[] }[]; systems: string[];
}

export interface Finding {
  id: string; verdict: string; kind?: string; as_of: string; depth: number; note?: string; created_at: string;
  superseded_by?: string | null; assignee?: string | null; label?: string;
}

export interface GateReason { code: string; text: string; premise?: string; evidence?: string; path?: PathNode[] }
export interface GateBasis { premise: string; text: string; path: PathNode[]; evidence: string | null; at: string | null }
export interface Snapshot { graph: string; as_of: string; digest: string; graph_digest?: string }

export interface Gate {
  gate: GateDecision; allowed: boolean; verdict: Verdict; reasons: GateReason[]; basis: GateBasis[];
  decision_id: string; title: string | null; as_of: string; depth: number; snapshot?: Snapshot; queries?: Query[];
  route?: { to: string; people: { id: string; name: string }[]; why: string } | null;
}

export interface MemoBroken {
  premise: { id: string; text: string }; stated: { id: string; text: string }; hops: number; state: PremiseState;
  path: PathNode[]; evidence: EvidenceEvent; reaffirmed_by: EvidenceEvent | null;
}

export interface Memo {
  found: boolean; decision: { id: string; title: string; decided_on: string }; verdict: Verdict; as_of: string; depth: number;
  broken: MemoBroken[]; affected: { id: string; title: string; verdict: Verdict; via: string; hops: number }[];
  owner: Owner | null; suggested_owner: { id: string | null; name: string | null; role: string | null; why: string };
  cites: string[]; text: string;
}

export interface DecisionResponse {
  audit: Audit; impact: Impact[]; findings: Finding[]; memo: Memo | null; gate: Gate; ticket: string; queries: Query[];
  /** Since when: every verdict the decision has had, re-audited on each date something in its subgraph happened. */
  history?: { verdict: Verdict; since: string | null; history: { verdict: Verdict; since: string | null }[] };
  /** Who knows why: owner, who wrote the record, who wrote evidence on a reason; bus_factor counts the people still here. */
  knowers?: { bus_factor: number; people: { id: string; name: string; active: boolean; left: string | null;
    roles: { how: string; what: string; reason?: string }[] }[] };
}

export interface LedgerRow {
  id: string; title: string; summary: string; decided_on: string; source?: string; owner: string | null; owner_id: string | null;
  owner_active: boolean; systems: string[]; verdict: Verdict; expired_premises: number;
}
export interface LedgerResponse { as_of: string; depth: number; decisions: LedgerRow[] }

export interface TimelinePoint {
  as_of: string; counts: Partial<Record<Verdict, number>>; moot: string[]; disputed: string[]; newly_moot: string[];
}
export interface TimelineResponse { depth: number; points: TimelinePoint[] }

export interface Candidate { id: string; title: string; summary: string; decided_on: string; score: number; matched_terms: number }

export interface AskResponse {
  outcome: "answered_with_path" | "answered_from_memory" | "not_in_graph" | "unknown_entity";
  question: string; candidates: Candidate[]; audit?: Audit; impact?: Impact[]; answer: string;
  narration?: "model" | "template" | "structural"; memory?: Finding | null; as_of?: string; depth?: number; queries?: Query[];
}

export interface TraceResponse {
  found: boolean; evidence: { id: string; title: string; date: string; excerpt?: string; kind?: string; path?: string };
  reaches: { id: string; title: string; hops: number; path: PathNode[] }[]; queries?: Query[];
}

export interface DocumentResponse { id: string; kind: string; title: string; date: string | null; author: string | null; path: string; text: string }

export interface OrphanDecision { id: string; title: string; verdict: Verdict; systems: string[]; decided_on: string;
  reasons: { id: string; text: string; state: PremiseState; hops: number }[] }
export interface OrphanGroup {
  person: { id: string; name: string; role: string; left: string };
  successor: { id: string; name: string; role: string; chain: { id: string; name: string; role: string; left: string }[]; hops: number } | null;
  decisions: OrphanDecision[];
}
export interface OrphansResponse { as_of: string; groups: OrphanGroup[]; count: number; queries?: Query[] }

export interface WhatIfDecision { id: string; title: string; hops: number; path: PathNode[]; before: Verdict; after: Verdict;
  flips: boolean; owner: string | null; systems: string[] }
export interface WhatIfResponse {
  found: boolean; premise?: { id: string; text: string; kind?: string }; as_of?: string; depth?: number; decisions?: WhatIfDecision[];
  would_fall?: number; already_moot?: number; systems?: string[];
  candidates?: { id: string; text: string; score: number; matched_terms: number; decisions?: number }[];
  question?: string | null; answer?: string; queries?: Query[];
}

export interface RiskyReason { id: string; text: string; kind: string; state: PremiseState; decisions: number; standing: number;
  decision_ids: string[]; systems: string[]; pagerank: number | null; rank: number; pagerank_rank: number }
export interface RiskyResponse { as_of: string; depth: number; reasons: RiskyReason[]; total: number }

export interface RealWorldDecision {
  id: string; title: string; repo: string; url: string; date: string; quote: string; status: string; verdict: Verdict;
  retired: { id: string; title: string; date: string; url: string; quote: string; commit: string } | null; gate: GateDecision;
  tools: { id: string; name: string; repo: string; unchecked: string[] }[];
  reasons: { id: string; text: string; state: PremiseState; unchecked?: string | null; evidence: EvidenceEvent[] }[];
}
export interface RealWorldResponse {
  summary: { checked_on: string; records: number; repos: number; tools: number; checks: number; failing: number; unchecked: number;
    retired?: number; dropped_records: string[]; dropped_retirements?: string[] };
  decisions: RealWorldDecision[]; shared: { tool: string; records: string[] }[]; queries?: Query[];
}

export interface HealthResponse { ok: boolean; tenant: string; stats: { nodes: Record<string, number>; edges: Record<string, number> }; model: boolean }

/** POST /api/answer: a question picks one read-only tool; `result` is that tool's rows. */
export type AnswerTool = "audit_decision" | "check_action" | "evidence_packet" | "what_if" | "decision_owner" | "orphaned_decisions" | "reopen_memo" | "ledger"
  | "who_knows_why" | "departure";
export interface PacketResult {
  found: boolean; decision: { id: string; title: string; decided_on: string }; verdict: Verdict; gate: GateDecision;
  reasons: GateReason[]; caveats: string[]; audit: Audit;
}
export interface OwnerResult { found: boolean; decision: DecisionNode | null; owner: Owner | null; group: OrphanGroup | null; held: LedgerRow[] }
export interface LedgerAnswer { as_of: string; depth: number; decisions: LedgerRow[]; verdict: Verdict | null; owner: { id: string; name: string; left: string } | null }
export type AnswerResult = Audit | Gate | PacketResult | WhatIfResponse | OwnerResult | OrphansResponse | (Memo & { audit?: Audit }) | LedgerAnswer;
export interface AnswerResponse {
  question: string; as_of: string; depth: number; tool: AnswerTool | null; input: Record<string, string>;
  why: string; matched: string | null; picked_by: "rules" | "model" | "you"; result: AnswerResult | null; queries: Query[];
}

/** GET /api/map: the whole network with each verdict and reason state at every month end (the map view). */
export interface MapNode {
  label: "Decision" | "Premise" | "Evidence" | "System" | "Person"; id: string;
  title?: string; text?: string; name?: string; role?: string; kind?: string; decided_on?: string; summary?: string;
  source?: string; author?: string | null; excerpt?: string; date?: string; left?: string;
}
export interface MapEdge { src: string; rel: string; dst: string; at?: string; quote?: string; stated?: string; valid_from?: string; valid_to?: string }
export interface MapPathRow { id: string; hops: number; state: PremiseState; path: string[] }
export interface MapData {
  tenant: string; as_of: string; depth: number; months: string[]; nodes: MapNode[]; edges: MapEdge[];
  pagerank: Record<string, number>; islands: Record<string, number>;
  verdicts: Record<string, (Verdict | null)[]>; premise_state: Record<string, (PremiseState | null)[]>;
  gate: Record<string, { action: GateDecision; reasons: { text: string }[] }>;
  owners: Record<string, { id: string; name: string; role: string; valid_to: string | null; active: boolean }>;
  paths: Record<string, MapPathRow[]>; queries: Record<string, string>;
}
