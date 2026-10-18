// The only way the UI talks to Moot: typed wrappers over the FastAPI routes. Reads never write; the three writes
// (findings, reopen, handover, ruling) are called only from an explicit approval click.
import type {
  AskResponse, DecisionResponse, DocumentResponse, Finding, Gate, HealthResponse, LedgerResponse, OrphansResponse,
  MapData, RealWorldResponse, RiskyResponse, TimelineResponse, TraceResponse, WhatIfResponse, AnswerResponse } from "./types";

export interface GraphInfo { name: string; title: string; kind: "demo" | "real" | "backtest" | "github"; source: string; decisions: number; default: boolean; as_of?: string; url?: string }
export interface GraphsResponse { graphs: GraphInfo[]; ingest: boolean }
export interface IngestSummary { repo: string; graph: string; folder: string; decisions: number; retired: number; people: number; pull_requests: number;
  verdicts: Record<string, number>; gates: Record<string, number>; moot: { id: string; title: string }[] }
export interface HistoryResponse { decision_id: string; as_of: string; verdict: string; since: string | null; history: { verdict: string; since: string | null }[] }

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

/** Eval results as committed. Only the fields the UI reads are typed; the rest is passed through. */
export interface EvalsResponse {
  retrieval?: { k: number; n: number; docs: number; graph_recall: number; bm25_recall: number; random_recall: number; graph_any: number; bm25_any: number; [k: string]: unknown };
  gate?: { as_of: string; methods: Record<string, { false_allows: string[]; false_blocks: string[]; stale_allowed: string[]; false_allow_upper95?: number }>; [k: string]: unknown };
  scale?: { scale: { n: number; docs: number; nodes: number; edges: number; graph: number; bm25: number; audit: { p50: number; p95: number }; ledger: { p50: number } }[]; [k: string]: unknown };
  ablation?: Record<string, unknown>;
  [k: string]: unknown;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

type Params = Record<string, string | number | boolean | null | undefined>;

function qs(p: Params = {}): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  const out = s.toString();
  return out ? `?${out}` : "";
}

// The graph every read and write goes to: the demo company by default, or any graph /api/graphs lists (the real ADRs,
// the backtest, an ingested GitHub repository). Set from the URL (?graph=) by AppStateProvider.
let GRAPH: string | null = null;
export const setGraph = (g: string | null) => { GRAPH = g; };
export const currentGraph = () => GRAPH;
const GLOBAL = /^\/api\/(graphs|evals|realworld|document|health|ingest)/;

function withGraph(path: string): string {
  if (!GRAPH || GLOBAL.test(path) || /[?&]graph=/.test(path)) return path;
  return `${path}${path.includes("?") ? "&" : "?"}graph=${encodeURIComponent(GRAPH)}`;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  path = withGraph(path);
  try {
    r = await fetch(`${API_BASE}${path}`, { ...init, headers: { "content-type": "application/json", ...(init?.headers ?? {}) } });
  } catch {
    throw new ApiError(0, "The Moot server is not reachable. Start it with `make serve`.");
  }
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* not json */ }
    throw new ApiError(r.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return r.json() as Promise<T>;
}

const get = <T,>(path: string, p?: Params) => call<T>(`${path}${qs(p)}`);
const post = <T,>(path: string, body: unknown) => call<T>(path, { method: "POST", body: JSON.stringify(body) });

export interface View { as_of?: string | null; depth?: number }

export const api = {
  health: () => get<HealthResponse>("/api/health"),
  ledger: (v: View = {}) => get<LedgerResponse>("/api/ledger", { as_of: v.as_of, depth: v.depth }),
  map: (v: View = {}) => get<MapData>("/api/map", { as_of: v.as_of, depth: v.depth }),
  timeline: (depth = 4) => get<TimelineResponse>("/api/timeline", { depth }),
  decision: (id: string, v: View = {}) => get<DecisionResponse>(`/api/decision/${encodeURIComponent(id)}`, { as_of: v.as_of, depth: v.depth }),
  gate: (id: string, as_of?: string | null, graph?: string) => get<Gate>(`/api/gate/${encodeURIComponent(id)}`, { as_of, graph }),
  packetUrl: (id: string, as_of?: string | null) => `${API_BASE}${withGraph(`/api/packet/${encodeURIComponent(id)}${qs({ as_of, format: "md" })}`)}`,
  graphs: () => get<GraphsResponse>("/api/graphs"),
  history: (id: string, v: View = {}) => get<HistoryResponse>(`/api/history/${encodeURIComponent(id)}`, { as_of: v.as_of, depth: v.depth }),
  search: (q: string) => get<{ id: string; title: string; summary: string; decided_on: string; score: number; matched_terms: number }[]>("/api/search", { q }),
  trace: (evidenceId: string) => get<TraceResponse>(`/api/trace/${encodeURIComponent(evidenceId)}`),
  document: (docId: string) => get<DocumentResponse>(`/api/document/${encodeURIComponent(docId)}`),
  ask: (question: string, v: View = {}) => post<AskResponse>("/api/ask", { question, as_of: v.as_of ?? null, depth: v.depth ?? 4 }),
  answer: (b: { question: string; tool?: string | null; input?: Record<string, string> } & View) =>
    post<AnswerResponse>("/api/answer", { question: b.question, tool: b.tool ?? null, input: b.input ?? null, as_of: b.as_of ?? null, depth: b.depth ?? 4 }),
  orphans: (v: View = {}) => get<OrphansResponse>("/api/orphans", { as_of: v.as_of, depth: v.depth }),
  whatif: (args: { premise?: string; q?: string } & View) =>
    get<WhatIfResponse>("/api/whatif", { premise: args.premise, q: args.q, as_of: args.as_of, depth: args.depth }),
  risky: (v: View & { limit?: number } = {}) => get<RiskyResponse>("/api/risky", { as_of: v.as_of, depth: v.depth, limit: v.limit }),
  realworld: () => get<RealWorldResponse>("/api/realworld"),
  /** Committed eval results (eval/results*.json): { retrieval, gate, scale, ablation }. See fixtures/evals.json. */
  evals: () => get<EvalsResponse>("/api/evals"),

  // Writes. Each one is behind a human approval click in the UI; nothing else may call these.
  recordFinding: (b: { decision_id: string; verdict: string; as_of: string; depth: number; cites: string[]; note?: string }) =>
    post<Finding & { cites: string[] }>("/api/findings", b),
  reopen: (b: { decision_id: string; as_of: string; depth: number; owner_id?: string | null }) =>
    post<Finding & { memo: unknown }>("/api/reopen", b),
  handover: (b: { decision_id: string; to: string; as_of: string }) =>
    post<{ decision_id: string; to: string; to_name?: string; from_id?: string | null; valid_from?: string; unchanged?: boolean }>("/api/handover", b),
  ingestGithub: (repo: string) => post<IngestSummary>("/api/ingest/github", { repo }),
  ruling: (b: { decision_id: string; premise_id: string; holds: boolean; as_of: string; by?: string | null; note?: string }) =>
    post<Record<string, unknown>>("/api/ruling", b),
};

export const today = () => new Date().toISOString().slice(0, 10);
