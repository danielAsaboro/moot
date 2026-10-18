"use client";
// Data for the agent gate page: one row per decision, built only from ledger, gate and realworld rows.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { VERDICT_ORDER } from "@/lib/format";
import type { Gate, GateDecision, LedgerRow, PremiseState, RealWorldDecision, Verdict } from "@/lib/types";

export type Source = "larkspur" | "public";

export interface GateItem {
  id: string;
  title: string;
  gate: GateDecision;
  verdict: Verdict;
  lead: string | null;      // the first reason (or, for Allow, the first basis row), in one line
  href: string;
  external: boolean;        // public records open their decision record on GitHub
}

export const OUTCOMES: GateDecision[] = ["DENY", "REVALIDATE", "ALLOW"];

export function leadFromGate(g: Gate): string | null {
  return g.reasons[0]?.text ?? g.basis[0]?.text ?? null;
}

const STATE_RANK: Record<PremiseState, number> = { expired: 0, disputed: 1, unchecked: 2, unevidenced: 3, holds: 4 };

export function itemFromLedger(row: LedgerRow, g: Gate, href: string): GateItem {
  return { id: row.id, title: g.title ?? row.title, gate: g.gate, verdict: g.verdict, lead: leadFromGate(g), href, external: false };
}

export function itemFromPublic(d: RealWorldDecision): GateItem {
  let lead: string | null = null;
  if (d.retired) lead = `Retired by ${d.retired.title}.`;
  else lead = [...d.reasons].sort((a, b) => STATE_RANK[a.state] - STATE_RANK[b.state])[0]?.text ?? null;
  return { id: d.id, title: d.title, gate: d.gate, verdict: d.verdict, lead, href: d.url, external: true };
}

export function byVerdictThenId(a: GateItem, b: GateItem) {
  const va = VERDICT_ORDER.indexOf(a.verdict); const vb = VERDICT_ORDER.indexOf(b.verdict);
  return (va === -1 ? 99 : va) - (vb === -1 ? 99 : vb) || a.id.localeCompare(b.id, undefined, { numeric: true });
}

/** Gate every ledger row, at most `limit` requests in flight. Restarts when the rows change. */
export function useGateRun(rows: LedgerRow[] | null, asOf: string | null, limit = 6) {
  const [gates, setGates] = useState<Record<string, Gate>>({});
  const [failed, setFailed] = useState<Record<string, string>>({});
  const run = useRef(0);

  const start = useCallback((ids: string[], fresh: boolean) => {
    const me = ++run.current;
    if (fresh) { setGates({}); }
    setFailed(f => (fresh ? {} : Object.fromEntries(Object.entries(f).filter(([k]) => !ids.includes(k)))));
    let next = 0;
    const worker = async () => {
      while (run.current === me && next < ids.length) {
        const id = ids[next++];
        try {
          const g = await api.gate(id, asOf);
          if (run.current === me) setGates(m => ({ ...m, [id]: g }));
        } catch (e) {
          if (run.current === me) setFailed(m => ({ ...m, [id]: (e as Error).message }));
        }
      }
    };
    for (let i = 0; i < Math.min(limit, ids.length); i++) void worker();
  }, [asOf, limit]);

  useEffect(() => {
    if (rows) start(rows.map(r => r.id), true);
    return () => { run.current++; };
  }, [rows, start]);

  const retry = useCallback(() => start(Object.keys(failed), false), [failed, start]);
  return { gates, failed, retry };
}
