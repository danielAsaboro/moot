"use client";
// Moot's memory: Finding nodes written back after an approval. One quiet row for the latest; tap for the history.
import { useCallback, useState } from "react";
import { Group, Row, Sheet, VerdictBadge } from "@/components/ui";
import { longDate, plural } from "@/lib/format";
import type { Finding, Verdict } from "@/lib/types";
import s from "./Audit.module.css";

const VERDICTS = new Set<string>(["HOLDS", "MOOT", "DISPUTED", "UNDOCUMENTED", "RETIRED", "NOT_YET", "NOT_IN_GRAPH"]);

/** "Re-opened 18 Oct 2026, assigned to Kwame Boateng" */
export function findingLine(f: Finding): string {
  const when = longDate(f.created_at);
  if (f.kind === "reopen") return `Re-opened ${when}${f.assignee ? `, assigned to ${f.assignee}` : ""}`;
  if (f.kind === "ruling") return `Owner ruling recorded ${when}`;
  return `Verdict recorded ${when}`;
}

export default function AuditMemory({ findings }: { findings: Finding[] }) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  if (!findings.length) return null;
  const latest = [...findings].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const top = latest[0];
  const badge = (f: Finding) => (VERDICTS.has(f.verdict) ? <VerdictBadge verdict={f.verdict as Verdict} /> : <span className="id">{f.verdict}</span>);

  return (
    <>
      <Group onSurface header={<h3 className={s.h}>Moot&apos;s memory</h3>} label="Moot's memory">
        <Row title={findingLine(top)}
          subtitle={latest.length > 1 ? `${plural(latest.length, "finding")} on record` : `As of ${longDate(top.as_of)}`}
          onClick={() => setOpen(true)} ariaLabel={`${findingLine(top)}. Show ${plural(latest.length, "finding")}`} />
      </Group>
      <Sheet open={open} title="Moot's memory" onClose={close}>
        <p className={s.sheetLead}>
          <span className="lead-in">Written only after an approval.</span> A newer finding supersedes an older one; nothing is deleted.
        </p>
        <Group header={`${plural(latest.length, "finding")}, latest first`}>
          {latest.map((f, i) => (
            <Row key={f.id} title={findingLine(f)} trailing={badge(f)}
              subtitle={<>
                <span className="id">{f.id}</span> · as of {longDate(f.as_of)}, depth {f.depth}
                {f.superseded_by ? " · superseded" : i === 0 ? " · current" : ""}
                {f.kind !== "reopen" && f.note ? ` · ${f.note}` : ""}
              </>} />
          ))}
        </Group>
      </Sheet>
    </>
  );
}
