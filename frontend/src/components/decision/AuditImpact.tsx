"use client";
// "Also resting on this reason": other decisions that rest on one of this decision's reasons that expired or is
// disputed. One row each: title, id and system, its own verdict pill, chevron to open it.
import { Group, Row, VerdictBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAppState } from "@/lib/appState";
import type { Impact, Premise, Verdict } from "@/lib/types";
import a from "./Audit.module.css";

export function impactGroups(decisionId: string, impact: Impact[]) {
  return impact
    .map(i => ({ ...i, others: i.decisions.filter(d => d.id !== decisionId) }))
    .filter(i => i.others.length > 0);
}

export default function AuditImpact({ groups, premises, verdicts = {}, asOf, depth }: {
  groups: ReturnType<typeof impactGroups>; premises: Premise[];
  /** Verdicts already known (from the re-open memo); the rest are read from the ledger at the same date and depth. */
  verdicts?: Record<string, Verdict>; asOf?: string; depth?: number;
}) {
  const { select } = useAppState();
  const ids = [...new Set(groups.flatMap(g => g.others.map(d => d.id)))];
  const missing = ids.some(id => !verdicts[id]);
  const ledger = useApi(
    () => (missing ? api.ledger({ as_of: asOf, depth }) : Promise.resolve(null)),
    [missing, asOf, depth],
  );
  const verdictOf = (id: string): Verdict | undefined =>
    verdicts[id] ?? ledger.data?.decisions.find(d => d.id === id)?.verdict;

  const many = groups.length > 1;
  const seen = new Set<string>();
  const rows = groups.flatMap(g => g.others.filter(d => (seen.has(d.id) ? false : (seen.add(d.id), true))).map(d => ({ d, g })));
  const stateWord = (pid: string) => premises.find(p => p.id === pid)?.state;

  return (
    <Group onSurface header={<h3 className={a.h}>{many ? "Also resting on these reasons" : "Also resting on this reason"}</h3>} label="Also resting on this reason">
      {rows.map(({ d, g }) => {
        const v = verdictOf(d.id);
        const via = many ? ` · via “${g.premise.text}”${stateWord(g.premise.id) === "disputed" ? " (disputed)" : ""}` : "";
        return (
          <Row key={d.id} title={d.title}
            subtitle={<><span className="id">{d.id}</span>{d.systems.length ? ` · ${d.systems.join(", ")}` : ""}{via}</>}
            trailing={v ? <VerdictBadge verdict={v} /> : undefined}
            onClick={() => select(d.id)} ariaLabel={`Open ${d.id}: ${d.title}${v ? `, ${v.toLowerCase()}` : ""}`} />
        );
      })}
    </Group>
  );
}
