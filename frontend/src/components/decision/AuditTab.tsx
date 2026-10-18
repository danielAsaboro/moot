"use client";
// The Summary view under the decision's segmented control: why it was made (reasons as rows, tap to expand), the
// evidence as exhibit cards, whether an agent may act on it (one row), what else rests on the same reason, Moot's
// memory, and one action at the bottom. Every write opens a sheet and waits for an approval.
import { useCallback, useState } from "react";
import { GateBadge, Group, Row, Sheet } from "@/components/ui";
import { api } from "@/lib/api";
import { plural } from "@/lib/format";
import type { DecisionResponse, Gate, Verdict } from "@/lib/types";
import PremiseBlock, { type ExhibitRef } from "./PremiseBlock";
import EvidenceExhibits, { collectExhibits } from "./EvidenceExhibits";
import AuditImpact, { impactGroups } from "./AuditImpact";
import AuditMemory from "./AuditMemory";
import AuditRecord, { canRecord } from "./AuditRecord";
import MemoReopen from "./MemoReopen";
import { NOTHING_WRITTEN } from "./AuditConfirm";
import s from "./Audit.module.css";

const CLAUSE: Record<string, string> = {
  premise_expired: "its reason expired",
  premise_disputed: "a reason is disputed",
  premise_unchecked: "a reason could not be checked",
  premise_unevidenced: "a reason has no evidence either way",
  owner_left: "the owner has left",
  undocumented: "no reason is recorded",
  retired: "it was retired",
  not_yet: "it is not decided yet",
  graph_has_no_evidence: "nothing in the graph was ever checked",
};

/** One line from the gate's first reason(s): "Its reason expired, and the owner has left." */
export function gateLine(gate: Gate): string {
  if (gate.allowed) return gate.basis.length ? "Every reason still holds." : "Nothing stands against it.";
  const codes = [...new Set(gate.reasons.map(r => r.code))].filter(c => CLAUSE[c]);
  if (!codes.length) return gate.reasons[0]?.text ?? "Re-validate it before anyone acts on it.";
  const second = codes.includes("owner_left") && codes[0] !== "owner_left" ? "owner_left" : codes[1];
  const parts = [CLAUSE[codes[0]], second && CLAUSE[second]].filter(Boolean) as string[];
  const line = parts.join(", and ");
  return `${line.charAt(0).toUpperCase()}${line.slice(1)}.`;
}

const H = ({ children, note }: { children: string; note?: string }) => (
  <h3 className={s.h}>{children}{note && <span className={s.hNote}> · {note}</span>}</h3>
);

export default function AuditTab({ data, onChanged, onGateDetails }: {
  data: DecisionResponse; onChanged: () => void;
  /** Opens the full gate sheet (owned by the panel). Without it, Details opens a short list of the gate's reasons. */
  onGateDetails?: () => void;
}) {
  const { audit, memo, findings, gate } = data;
  const d = audit.decision;
  const exhibits = collectExhibits(d.id, audit.premises);
  const refs = (premiseId: string): ExhibitRef[] =>
    exhibits.filter(x => x.premise.id === premiseId).map(x => ({ n: x.n, anchor: x.anchor, rel: x.ev.rel, at: x.ev.at, id: x.ev.id }));
  const groups = impactGroups(d.id, data.impact);
  const hasMemo = !!memo && memo.broken.length > 0;
  const known: Record<string, Verdict> = Object.fromEntries((memo?.affected ?? []).map(x => [x.id, x.verdict]));
  const [gateOpen, setGateOpen] = useState(false);
  const closeGate = useCallback(() => setGateOpen(false), []);
  const showAction = hasMemo || canRecord(audit);

  return (
    <div className={s.tab}>
      <Group onSurface header={<H>Why it was made</H>} label="Why it was made">
        {audit.premises.length ? audit.premises.map(p => (
          <PremiseBlock key={p.id} premise={p} exhibits={refs(p.id)} decisionId={d.id} asOf={audit.as_of}
            owner={audit.owner} onChanged={onChanged} />
        )) : (
          <Row title="No reason is recorded" subtitle="The source gives no reason, so there is nothing to check it against." />
        )}
      </Group>

      {exhibits.length > 0 && (
        <section className={s.section} aria-label="The evidence">
          <div className={s.sectionHead}><H note={exhibits.length > 1 ? `${plural(exhibits.length, "exhibit")}, turn one over for the quote` : "turn a card over for the quote"}>The evidence</H></div>
          <EvidenceExhibits exhibits={exhibits} decisionId={d.id} decidedOn={d.decided_on} asOf={audit.as_of} />
        </section>
      )}

      {gate && (
        <Group onSurface header={<H>Can an agent act on it?</H>} label="Can an agent act on it?">
          <Row leading={<GateBadge gate={gate.gate} size="md" />} title={<span className={s.gateLine}>{gateLine(gate)}</span>}
            trailing={
              <button type="button" className="btn plain small" onClick={onGateDetails ?? (() => setGateOpen(true))}
                aria-label="Details of the agent gate">Details</button>
            } />
        </Group>
      )}

      {groups.length > 0 && (
        <AuditImpact groups={groups} premises={audit.premises} verdicts={known} asOf={audit.as_of} depth={audit.depth} />
      )}

      <AuditMemory findings={findings} />

      {showAction && (
        <footer className={s.action}>
          {hasMemo && memo ? <MemoReopen memo={memo} audit={audit} onChanged={onChanged} /> : <AuditRecord audit={audit} onChanged={onChanged} />}
          <span className="t-footnote">{NOTHING_WRITTEN}</span>
        </footer>
      )}

      {gate && !onGateDetails && (
        <Sheet open={gateOpen} title="Agent gate" onClose={closeGate}>
          <p className={s.sheetLead}><span className="lead-in">{gateLine(gate)}</span> The gate reads the same rows as the verdict.</p>
          <Group header={gate.allowed ? "Why it may act" : plural(gate.reasons.length, "reason")}>
            {gate.allowed
              ? gate.basis.map(b => <Row key={b.premise} title={b.text} subtitle={b.evidence ? <>Latest support <span className="id">{b.evidence}</span></> : "Stated in the record; nothing contradicts it"} />)
              : gate.reasons.map((r, i) => <Row key={`${r.code}-${r.premise ?? i}`} title={r.text} />)}
          </Group>
          <a className="btn ghost" href={api.packetUrl(gate.decision_id, audit.as_of)} download>Download evidence packet</a>
        </Sheet>
      )}
    </div>
  );
}
