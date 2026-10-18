"use client";
// One decision on the agent gate page, as a list row: title, the first reason in one line, the verdict, a chevron.
// Larkspur rows open the decision; public records open their decision record on GitHub.
import { Row, VerdictBadge } from "@/components/ui";
import type { GateItem } from "./gateData";
import s from "./GateBoard.module.css";

function Subtitle({ item }: { item: GateItem }) {
  return (
    <span className={s.sub}>
      <span className="id">{item.id}</span>
      <span aria-hidden="true"> · </span>
      {item.lead ?? "No reason recorded."}
    </span>
  );
}

export default function GateCard({ item }: { item: GateItem }) {
  if (!item.external) {
    return <Row title={item.title} subtitle={<Subtitle item={item} />} trailing={<VerdictBadge verdict={item.verdict} />} href={item.href} />;
  }
  return (
    <a className={s.ext} href={item.href} target="_blank" rel="noopener noreferrer">
      <span className={s.extMain}>
        <span className={s.extTitle}>{item.title}</span>
        <span className={s.extSub}><Subtitle item={item} /></span>
      </span>
      <VerdictBadge verdict={item.verdict} />
      <span className={s.chev} aria-hidden="true">›</span>
      <span className="sr-only">(opens the record on GitHub)</span>
    </a>
  );
}
