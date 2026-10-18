"use client";
// The re-open memo as a sheet: which reason broke, the evidence that broke it, what else rests on it and who should
// own the follow-up. Approving writes one re-open Finding; the server rebuilds the memo from the graph, so the text
// cannot drift from the rows.
import { useState, type ReactNode } from "react";
import { Group, Row, VerdictBadge, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { longDate } from "@/lib/format";
import type { Audit, Memo } from "@/lib/types";
import AuditConfirm, { useConfirm } from "./AuditConfirm";
import s from "./Memo.module.css";

const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]?.toUpperCase()).join("");

/** "D02 and D03", "D02, D04 and D07" */
function idList(ids: string[]) {
  return ids.length <= 1 ? ids.join("") : `${ids.slice(0, -1).join(", ")} and ${ids[ids.length - 1]}`;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <><span className={s.fieldLabel}>{label}</span>{children}</>;
}

export default function MemoReopen({ memo, audit, onChanged }: { memo: Memo; audit: Audit; onChanged: () => void }) {
  const { open, show, close, state, run } = useConfirm(onChanged);
  const [copy, setCopy] = useState<"idle" | "ok" | "failed">("idle");
  const owner = memo.suggested_owner;
  const first = owner.name?.split(" ")[0] ?? null;
  const id = audit.decision.id;
  const left = memo.owner && !memo.owner.active ? memo.owner : null;
  const why = left && first && /reporting line/i.test(owner.why)
    ? `${left.name} left${left.valid_to ? ` on ${longDate(left.valid_to)}` : ""}; ${first} is next up the reporting line.`
    : owner.why;

  const approve = () => void run(async () => {
    const r = await api.reopen({ decision_id: id, as_of: audit.as_of, depth: audit.depth, owner_id: owner.id });
    return `Re-opened ${id}. Finding ${r.id} is written${owner.name ? ` and assigned to ${owner.name}` : ""}.`;
  });

  const copyText = async () => {
    try { await navigator.clipboard.writeText(memo.text); setCopy("ok"); } catch { setCopy("failed"); }
  };
  const openSheet = () => { setCopy("idle"); show(); };

  return (
    <>
      <button type="button" className="btn accent" onClick={openSheet}>{first ? `Re-open with ${first}…` : "Re-open…"}</button>
      <AuditConfirm open={open} title={`Re-open ${id}`} onClose={close} state={state} onApprove={approve}
        approveLabel="Approve and re-open"
        action={<button type="button" className="btn plain" onClick={copyText}>Copy</button>}
        footnote={`Writes one Finding to the graph${first ? `, assigned to ${first}` : ", with no assignee"}.`}>
        <Group label="What broke">
          {memo.broken.map(b => (
            <Row key={`r-${b.premise.id}`}
              title={<Field label={b.state === "disputed" ? "Reason in dispute" : "Reason that broke"}>{b.premise.text}</Field>}
              subtitle={b.hops > 1 ? `Behind the stated reason, “${b.stated.text}”.` : undefined} />
          ))}
          {memo.broken.map(b => (
            <Row key={`e-${b.premise.id}-${b.evidence.id}`}
              title={<Field label="New evidence"><span className="id">{b.evidence.id}</span>, {longDate(b.evidence.at)}</Field>}
              subtitle={<>
                {b.evidence.title}
                {b.reaffirmed_by && <> · re-affirmed {longDate(b.reaffirmed_by.at)} by <span className="id">{b.reaffirmed_by.id}</span>, so disputed, not dead</>}
              </>} />
          ))}
          <Row
            title={<Field label="Also affected">{memo.affected.length ? idList(memo.affected.map(x => x.id)) : "Nothing else"}</Field>}
            subtitle={memo.affected.length ? memo.affected.map(x => x.title).join(" · ") : "No other decision rests on this reason."}
            trailing={memo.affected.length && memo.affected.every(x => x.verdict === memo.affected[0].verdict)
              ? <VerdictBadge verdict={memo.affected[0].verdict} /> : undefined} />
        </Group>

        <Group label="Assignee">
          <Row leading={<span className={s.avatar} aria-hidden="true">{owner.name ? initials(owner.name) : "?"}</span>}
            title={owner.name ? `Assign to ${owner.name}` : "No one to assign"}
            subtitle={why} />
        </Group>

        <p role="status" className={cx(s.copy, copy === "failed" && s.copyFailed)}>
          {copy === "ok" ? "Memo copied." : copy === "failed" ? "Copy is blocked here. The memo text is below." : ""}
        </p>
        {copy === "failed" && <pre className={s.plain} tabIndex={0} aria-label="Memo as plain text">{memo.text}</pre>}
      </AuditConfirm>
    </>
  );
}
