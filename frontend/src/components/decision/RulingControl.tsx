"use client";
// Owner ruling on a reason the gate could not vouch for (disputed, unchecked, unevidenced). The approval writes a dated
// SUPPORTS or CONTRADICTS edge from a Finding to the premise; the next audit reads it like any evidence.
import { useState } from "react";
import { Group, Row, Segmented } from "@/components/ui";
import { api } from "@/lib/api";
import { longDate } from "@/lib/format";
import type { Owner, Premise } from "@/lib/types";
import AuditConfirm, { NOTHING_WRITTEN, useConfirm } from "./AuditConfirm";
import s from "./Premise.module.css";

type Choice = "" | "holds" | "broken";

function signer(owner: Owner | null): { by: string | null; line: string } {
  if (!owner) return { by: null, line: "Unsigned: there is no owner of record." };
  if (!owner.active) return { by: null, line: `Unsigned: the owner of record, ${owner.name}, left${owner.valid_to ? ` on ${longDate(owner.valid_to)}` : ""}.` };
  return { by: owner.id, line: `Signed by ${owner.name}${owner.role ? `, ${owner.role}` : ""}.` };
}

export default function RulingControl({ decisionId, premise, asOf, owner, onChanged }: {
  decisionId: string; premise: Premise; asOf: string; owner: Owner | null; onChanged: () => void;
}) {
  const { open, show, close, state, run } = useConfirm(onChanged);
  const [choice, setChoice] = useState<Choice>("");
  const [note, setNote] = useState("");
  const { by, line } = signer(owner);
  const done = state.phase === "done";

  const rule = () => {
    if (!choice) return;
    const holds = choice === "holds";
    void run(async () => {
      const r = await api.ruling({ decision_id: decisionId, premise_id: premise.id, holds, as_of: asOf, by, note: note.trim() || "ruled in UI" });
      const rel = typeof r.rel === "string" ? r.rel : holds ? "SUPPORTS" : "CONTRADICTS";
      const gate = typeof r.gate === "string" ? ` The agent gate now answers ${r.gate.charAt(0)}${r.gate.slice(1).toLowerCase()}.` : "";
      return `Ruling recorded: a ${rel === "SUPPORTS" ? "supporting" : "contradicting"} edge dated ${longDate(asOf)}${typeof r.id === "string" ? ` from ${r.id}` : ""}.${gate}`;
    });
  };

  const open_ = () => { setChoice(""); setNote(""); show(); };

  return (
    <>
      <button type="button" className={`btn plain ${s.ruleBtn}`} onClick={open_}>Rule on this reason…</button>
      <AuditConfirm open={open} title="Owner ruling" onClose={close} state={state} onApprove={rule} canApprove={!!choice}
        approveLabel="Approve ruling"
        footnote={choice
          ? `Writes one dated ${choice === "holds" ? "Supports" : "Contradicts"} edge from a Finding, as of ${longDate(asOf)}.`
          : NOTHING_WRITTEN}>
        <Group header="Reason">
          <Row title={premise.text} subtitle={<span className="id">{premise.id}</span>} />
          <Row title={line} subtitle={`As of ${longDate(asOf)}`} />
        </Group>
        {!done && (
          <div className={s.choice}>
            <span className="t-footnote" id={`rule-${premise.id}`}>Does it still hold?</span>
            <Segmented<Choice> label="Does this reason still hold?" value={choice} onChange={setChoice}
              options={[["holds", "It still holds"], ["broken", "It no longer holds"]]} />
          </div>
        )}
        {!done && (
          <label className={s.noteLabel}>
            <span className="t-footnote">Note, cited with the edge (optional)</span>
            <input className="input" value={note} maxLength={500} onChange={e => setNote(e.target.value)} placeholder="Why, in one line" />
          </label>
        )}
      </AuditConfirm>
    </>
  );
}
