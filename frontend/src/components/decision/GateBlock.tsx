"use client";
// The agent gate in full: may an agent act on this decision, every reason (or what it rests on), the call and the
// snapshot it was answered from, and the evidence packet. Shown on tap, in a sheet (`GateSheet`).
import type { ReactNode } from "react";
import type { Gate, PathNode } from "@/lib/types";
import { api } from "@/lib/api";
import { gateSummary, longDate, plural } from "@/lib/format";
import { GateBadge, Group, Row, Sheet } from "@/components/ui";
import s from "./GateBlock.module.css";

/** Readable dates, curly quotes, and every id the row returned (PR-412, chat-2026-07-09-ld, D09) set in mono. */
const ID = /((?<![\w-])(?:[A-Za-z]+-[\w-]*\d[\w-]*|D\d{2,})(?![\w-]))/;
function prose(text: string, id?: string | null): ReactNode {
  const t = text.replace(/(?<![\w-])\d{4}-\d{2}-\d{2}(?![\w-])/g, m => longDate(m)).replace(/"([^"]*)"/g, "\u201c$1\u201d");
  const parts = t.split(id ? new RegExp(`(${id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})|${ID.source}`) : ID).filter(p => p !== undefined && p !== "");
  return <>{parts.map((p, i) => (p === id || new RegExp(`^${ID.source}$`).test(p) ? <span key={i} className="id">{p}</span> : p))}</>;
}

const through = (path?: PathNode[]) => (path && path.length > 2 ? `Through ${plural(path.length - 1, "hop")}` : undefined);
const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

export default function GateBlock({ gate, asOf }: { gate: Gate; asOf: string | null }) {
  const summary = gateSummary(gate.gate, gate.reasons[0]?.code);
  return (
    <div className={s.gate}>
      <div className={s.head}>
        <GateBadge gate={gate.gate} size="md" />
        <p className={`t-title3 ${s.sum}`}>{cap(summary)}.</p>
      </div>

      {gate.allowed ? (
        gate.basis.length > 0 && (
          <Group header="What it rests on" label="What it rests on">
            {gate.basis.map(b => (
              <Row key={b.premise} title={`“${b.text}” holds.`}
                subtitle={<>{b.evidence ? <>Latest support <span className="id">{b.evidence}</span> on {longDate(b.at)}</> : "Stated in the record; nothing contradicts it"}
                  {through(b.path) && <> · {through(b.path)}</>}</>} />
            ))}
          </Group>
        )
      ) : (
        gate.reasons.length > 0 && (
          <Group header={gate.reasons.length > 1 ? `${gate.reasons.length} reasons` : "Reason"} label="Reasons">
            {gate.reasons.map((r, i) => (
              <Row key={`${r.code}-${r.premise ?? i}`} title={prose(r.text, r.evidence)} subtitle={through(r.path)} />
            ))}
          </Group>
        )
      )}

      <Group header="The call" label="The call"
        footer={gate.snapshot ? <span>Answered from <span className="id">{gate.snapshot.graph}</span> as of {longDate(gate.as_of)}, digest <span className="id">{gate.snapshot.digest}</span>.</span> : undefined}>
        <Row title={<span className="id">GET /api/gate/{gate.decision_id}</span>} subtitle={`Audited ${plural(gate.depth, "hop")} deep`} />
      </Group>

      <a className="btn ghost small" href={api.packetUrl(gate.decision_id, asOf)} download>Download evidence packet</a>
    </div>
  );
}

/** The gate, opened on tap from a "Details" link. Read-only: it writes nothing. */
export function GateSheet({ gate, asOf, open, onClose }: { gate: Gate; asOf: string | null; open: boolean; onClose: () => void }) {
  return (
    <Sheet open={open} onClose={onClose} title="Can an agent act on it?" cancelLabel="Done">
      <GateBlock gate={gate} asOf={asOf} />
    </Sheet>
  );
}
