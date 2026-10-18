"use client";
// Every dated evidence event behind the audit, as numbered exhibit cards.
import type { EvidenceEvent, Premise } from "@/lib/types";
import EvidenceCard from "./EvidenceCard";
import s from "./Evidence.module.css";

export interface Exhibit { n: number; anchor: string; ev: EvidenceEvent; premise: Premise }

/** Number the events in premise order, then by date; the same edge is listed once. */
export function collectExhibits(decisionId: string, premises: Premise[]): Exhibit[] {
  const seen = new Set<string>();
  const out: Exhibit[] = [];
  for (const p of premises) {
    for (const ev of [...p.evidence].sort((a, b) => a.at.localeCompare(b.at))) {
      const key = `${ev.id}|${p.id}|${ev.rel}|${ev.at}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const n = out.length + 1;
      out.push({ n, anchor: `exhibit-${decisionId}-${n}`, ev, premise: p });
    }
  }
  return out;
}

export default function EvidenceExhibits({ exhibits, decisionId, decidedOn, asOf }: {
  exhibits: Exhibit[]; decisionId: string; decidedOn: string; asOf: string;
}) {
  return (
    <ol className={s.grid}>
      {exhibits.map(x => (
        <EvidenceCard key={x.anchor} n={x.n} ev={x.ev} premise={x.premise} anchor={x.anchor}
          decisionId={decisionId} decidedOn={decidedOn} asOf={asOf} />
      ))}
    </ol>
  );
}
