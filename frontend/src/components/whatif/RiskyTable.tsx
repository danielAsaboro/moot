"use client";
// Riskiest reasons: premises ranked by how many standing decisions rest on them, as a grouped list. Tapping one tests it.
import type { RiskyReason, RiskyResponse } from "@/lib/types";
import { longDate, plural } from "@/lib/format";
import { Group, Row, StateTag } from "@/components/ui";
import s from "./whatif.module.css";

function carries(r: RiskyReason): string {
  const all = r.decisions > r.standing ? ` of ${r.decisions}` : "";
  const systems = r.systems.map(x => x.toLowerCase()).join(", ");
  return `carries ${plural(r.standing, "standing decision")}${all}${systems ? ` · ${systems}` : ""}`;
}

export default function RiskyTable({ data, current, onTest }: { data: RiskyResponse; current: string | null; onTest: (id: string) => void }) {
  return (
    <Group label={`Riskiest reasons as of ${data.as_of}`}
      footer={<span>Top {data.reasons.length} of {data.total} reasons, as of {longDate(data.as_of)}, up to {plural(data.depth, "hop")}.</span>}>
      {data.reasons.map(r => (
        <Row key={r.id} title={r.text} subtitle={carries(r)} trailing={<span className={s.state}><StateTag state={r.state} /></span>}
          onClick={() => onTest(r.id)} selected={current === r.id} />
      ))}
    </Group>
  );
}
