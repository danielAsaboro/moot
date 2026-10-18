"use client";
// One decision the leaver held: its lanyard badge (drag to the successor), title, system, verdict pill and a plain
// "Hand to <name>" button. Both only ask the page to open its approval sheet; nothing is written here.
import Link from "next/link";
import type { OrphanDecision } from "@/lib/types";
import { VerdictBadge } from "@/components/ui";
import { longDate } from "@/lib/format";
import LanyardBadge from "./LanyardBadge";
import type { DropState } from "./ReportingLine";
import s from "./orphans.module.css";

interface Props {
  d: OrphanDecision;
  href: string;
  successor: { id: string; name: string } | null;
  confirming?: boolean;               // its approval sheet is open
  busy?: boolean;                     // a handover is being written
  getTarget: () => HTMLElement | null;
  onDragState: (state: DropState) => void;
  onAsk: () => void;                  // open the approval sheet (drop or button)
}

export default function OrphanRow({ d, href, successor, confirming = false, busy = false, getTarget, onDragState, onAsk }: Props) {
  const first = successor?.name.split(" ")[0] ?? "";
  return (
    <li className={s.row}>
      <LanyardBadge
        id={d.id}
        disabled={!successor || busy}
        hint={successor ? `Drag onto ${successor.name} to hand over ${d.id}` : ""}
        getTarget={getTarget}
        onDragState={onDragState}
        onDrop={onAsk}
      />
      <div className={s.rowMain}>
        <Link href={href} className={s.title}><span className="sr-only">{d.id}: </span>{d.title}</Link>
        <span className={s.sub}>
          {[d.systems.join(", "), d.decided_on && `decided ${longDate(d.decided_on)}`].filter(Boolean).join(" · ")}
        </span>
      </div>
      <div className={s.rowEnd}>
        <VerdictBadge verdict={d.verdict} />
        {successor && (
          <button
            type="button"
            className={`btn plain small ${s.handBtn}`}
            onClick={onAsk}
            disabled={busy}
            aria-haspopup="dialog"
            aria-expanded={confirming}
            aria-label={`Hand ${d.id} to ${successor.name}`}
          >
            Hand to {first}
          </button>
        )}
      </div>
    </li>
  );
}
