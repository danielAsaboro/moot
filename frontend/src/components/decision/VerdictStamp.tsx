"use client";
// The verdict, said once: one plain sentence built from the audit rows (the deciding reason, its dated evidence),
// and one grey line (decided, owner, as of, depth). Nothing here is computed that the graph did not return.
import type { ReactNode } from "react";
import type { Audit, EvidenceEvent, Gate, Premise, PremiseState } from "@/lib/types";
import { VerdictBadge, decidingEvent } from "@/components/ui";
import { longDate as shortDate, plural } from "@/lib/format";
import s from "./VerdictStamp.module.css";

/** "2026-03-02" -> "2 March 2026" (the sentence reads better with the month spelled out). */
export function fullDate(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
}

const Id = ({ children }: { children: ReactNode }) => <span className="id">{children}</span>;

/** The premises whose state decides the verdict, each with the dated event that decided it. */
function deciding(audit: Audit): { premise: Premise; event: EvidenceEvent | null }[] {
  const want: Partial<Record<string, PremiseState>> = { MOOT: "expired", DISPUTED: "disputed", HOLDS: "holds" };
  const state = want[audit.verdict];
  if (!state) return [];
  const rows = audit.premises.filter(p => p.state === state).map(p => ({ premise: p, event: decidingEvent(p.evidence) }));
  const at = (r: { event: EvidenceEvent | null }) => r.event?.at ?? "";
  // MOOT: the first contradiction is when the decision went moot. Otherwise the newest event is the current word.
  rows.sort((a, b) => (audit.verdict === "MOOT" ? at(a).localeCompare(at(b)) : at(b).localeCompare(at(a))));
  return rows;
}

const verb = (e: EvidenceEvent) => (e.rel === "CONTRADICTS" ? "contradicted" : "backed");

/** The lead phrase and the continuation of the one sentence that says why. */
function why(audit: Audit, onSelect?: (id: string) => void): [string, ReactNode] {
  const v = audit.verdict;
  const rows = deciding(audit);
  const top = rows[0];
  if (v === "MOOT") {
    const subject = rows.length > 1 ? `${rows.length} of its reasons have expired. The first` : "Its reason";
    const e = top?.event;
    if (!e) return ["This rule is moot.", rows.length > 1 ? `${rows.length} of its reasons no longer hold.`
      : top ? <>Its reason, “{top.premise.text}”, no longer holds.</> : "Its reason no longer holds."];
    const before = e.at < audit.decision.decided_on;
    return ["This rule is moot.", before
      ? <>{subject} was already contradicted on {fullDate(e.at)}, before the rule was made, by <Id>{e.id}</Id>: “{e.title}.”</>
      : <>{subject} expired on {fullDate(e.at)}, when <Id>{e.id}</Id> contradicted it: “{e.title}.”</>];
  }
  if (v === "DISPUTED") {
    const p = top?.premise;
    const last = (rel: string) => [...(p?.evidence ?? [])].filter(x => x.rel === rel).pop();
    const pair = [last("CONTRADICTS"), last("SUPPORTS")].filter((x): x is EvidenceEvent => !!x).sort((a, b) => a.at.localeCompare(b.at));
    if (pair.length < 2) return ["This rule is disputed.", "The evidence on its reason points both ways. Its owner has to rule."];
    const [a, b] = pair;
    return ["This rule is disputed.",
      <><Id>{a.id}</Id> {verb(a)} its reason on {fullDate(a.at)}, then <Id>{b.id}</Id> {verb(b)} it on {fullDate(b.at)}. Its owner has to rule.</>];
  }
  if (v === "HOLDS") {
    const e = rows.map(r => r.event).find((x): x is EvidenceEvent => !!x && x.rel === "SUPPORTS");
    return ["This rule still holds.", e
      ? <>Its reason was last confirmed on {fullDate(e.at)} by <Id>{e.id}</Id>: “{e.title}.”</>
      : "Nothing on record contradicts its reasons."];
  }
  if (v === "UNDOCUMENTED") return ["This rule is undocumented.", "The record gives no reason for it, so there is nothing to check."];
  if (v === "RETIRED") {
    const sup = audit.superseded_by;
    if (!sup) return ["This rule is retired.", "It no longer stands, so there is nothing to audit."];
    const ref = sup.kind === "decision" && onSelect
      ? <button type="button" className={s.ref} onClick={() => onSelect(sup.id)}><Id>{sup.id}</Id>, “{sup.title}”</button>
      : <><Id>{sup.id}</Id>, “{sup.title}”</>;
    return ["This rule is retired.", <>{ref} replaced it on {fullDate(sup.at)}.</>];
  }
  if (v === "NOT_YET") {
    return ["This rule had not been made yet.", <>It was decided on {fullDate(audit.decision.decided_on)}, after the date you are viewing ({fullDate(audit.as_of)}). Move the date forward to audit it.</>];
  }
  return ["This rule is not in the graph.", "Moot only audits decisions it has a record of."];
}

/** The one plain sentence: bold lead-in, then the reason with its id and date. */
export function VerdictWhy({ audit, onSelect, className }: { audit: Audit; onSelect?: (id: string) => void; className?: string }) {
  const [lead, rest] = why(audit, onSelect);
  return <p className={className ?? s.why}><span className="lead-in">{lead}</span> {rest}</p>;
}

/** One grey line: "Decided 10 Feb 2025 by Ada Okafor, who left on 15 May 2026. As of 16 Oct 2026, 4 hops deep." */
export function VerdictMeta({ audit, className }: { audit: Audit; className?: string }) {
  const o = audit.owner;
  const longDate = (iso?: string | null) => shortDate(iso).replace(/ /g, "\u00a0");   // keep "15 May 2026" on one line
  const by = o ? <> by {o.name}{!o.active && o.valid_to ? `, who left on ${longDate(o.valid_to)}` : ""}.</> : ". No owner on record.";
  const deep = audit.verdict === "NOT_YET" ? "" : `, ${plural(audit.depth, "hop")} deep`;
  return <p className={className ?? "t-sub"} style={{ margin: 0 }}>Decided {longDate(audit.decision.decided_on)}{by} As of {longDate(audit.as_of)}{deep}.</p>;
}

/** Compact verdict mark: the solid pill and the sentence. `gate` is accepted for older callers; the gate is shown elsewhere. */
export default function VerdictStamp({ audit, gate }: { audit: Audit; gate: Gate | null }) {
  void gate;
  return (
    <div className={s.stamp}>
      <VerdictBadge verdict={audit.verdict} fill size="md" />
      <VerdictWhy audit={audit} />
    </div>
  );
}
