// The ruled-ledger field's model: one token per ledger row, laid out in reading order by decision date,
// and each token's state at a timeline point. Shared by the 3D field and its 2D fallback.
import type { LedgerRow, TimelinePoint } from "@/lib/types";

export type TokenState = "ghost" | "float" | "moot"; // ghost = not decided yet as of the point

export interface FieldToken { id: string; title: string; decided_on: string; col: number; row: number }

export function layoutTokens(rows: LedgerRow[], cols: number): FieldToken[] {
  return [...rows]
    .sort((a, b) => a.decided_on.localeCompare(b.decided_on) || a.id.localeCompare(b.id))
    .map((r, i) => ({ id: r.id, title: r.title, decided_on: r.decided_on, col: i % cols, row: Math.floor(i / cols) }));
}

export function tokenStates(tokens: FieldToken[], point: TimelinePoint | undefined): TokenState[] {
  if (!point) return tokens.map(() => "float");
  const moot = new Set(point.moot);
  return tokens.map(t => (t.decided_on > point.as_of ? "ghost" : moot.has(t.id) ? "moot" : "float"));
}

export const decisionHref = (id: string, asOf: string) => `/app/?d=${encodeURIComponent(id)}&as_of=${asOf}&depth=4`;
