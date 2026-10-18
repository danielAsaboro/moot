"use client";
// "Record this verdict": write the current verdict as a Finding node, citing the contradicting evidence, after an
// approval in a sheet.
import { Group, Row, VerdictBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { longDate } from "@/lib/format";
import type { Audit } from "@/lib/types";
import AuditConfirm, { useConfirm } from "./AuditConfirm";

const RECORDABLE = new Set(["MOOT", "DISPUTED", "HOLDS", "UNDOCUMENTED", "RETIRED"]);
export const canRecord = (audit: Audit) => RECORDABLE.has(audit.verdict);

export default function AuditRecord({ audit, onChanged }: { audit: Audit; onChanged: () => void }) {
  const { open, show, close, state, run } = useConfirm(onChanged);
  const id = audit.decision.id;
  const cites = [...new Set(audit.premises.flatMap(p => p.evidence.filter(e => e.rel === "CONTRADICTS" && !e.ruling).map(e => e.id)))];

  if (!canRecord(audit)) return null;

  const record = () => void run(async () => {
    const r = await api.recordFinding({ decision_id: id, verdict: audit.verdict, as_of: audit.as_of, depth: audit.depth, cites, note: "approved in UI" });
    return `Recorded. Finding ${r.id} now holds this verdict for ${id}.`;
  });

  return (
    <>
      <button type="button" className="btn ghost" onClick={show}>Record this verdict</button>
      <AuditConfirm open={open} title={`Record ${id}`} onClose={close} state={state} onApprove={record}
        approveLabel="Approve and record" footnote="Writes one Finding to the graph. Earlier findings are superseded, not deleted.">
        <Group>
          <Row title="Verdict" trailing={<VerdictBadge verdict={audit.verdict} />} />
          <Row title="As of" trailing={<span className="t-sub">{longDate(audit.as_of)}, depth {audit.depth}</span>} />
          <Row title="Cites" trailing={<span className="t-sub">{cites.length ? <span className="id">{cites.join(", ")}</span> : "No contradicting evidence"}</span>} />
          <Row title="Note" trailing={<span className="t-sub">Approved in UI</span>} />
        </Group>
      </AuditConfirm>
    </>
  );
}
