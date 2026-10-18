"use client";
// The reporting line as it stood on the day the owner left, from the leaver to the first person still here, as soft
// chips. People who left are struck through; the successor's chip (ink ring) is where a lanyard badge is dropped.
import type { Ref } from "react";
import type { OrphanGroup } from "@/lib/types";
import { longDate } from "@/lib/format";
import { cx } from "@/components/ui";
import s from "./orphans.module.css";

export type DropState = "idle" | "dragging" | "over";

interface Props {
  group: OrphanGroup;
  asOf: string;
  dropRef: Ref<HTMLDivElement>;
  drop: DropState;
  dragging: string | null;   // decision id being dragged in this group
}

const STEPS = ["no steps", "one step", "two steps", "three steps", "four steps", "five steps"];
export const firstName = (name: string) => name.split(/\s+/)[0] ?? name;

export default function ReportingLine({ group, asOf, dropRef, drop, dragging }: Props) {
  const succ = group.successor;
  if (!succ) {
    return (
      <div className={s.line}>
        <p className={s.nobody}>
          <b>Nobody to hand to.</b> Nobody in {group.person.name}&apos;s reporting line on {longDate(group.person.left) || "the day they left"} is still here.
        </p>
      </div>
    );
  }
  const last = succ.chain.length - 1;
  const first = firstName(succ.name);
  const steps = STEPS[succ.hops] ?? `${succ.hops} steps`;
  const note = drop === "over"
    ? <><b>Release to hand {dragging ?? "it"} to {first}.</b></>
    : drop === "dragging"
      ? <><b>Drop the badge on {first}.</b></>
      : <>{succ.role ? `${succ.role}, ` : ""}{steps} up.</>;

  return (
    <div className={s.line}>
      <span className="sr-only">Reporting line on {longDate(group.person.left)}, up to the first person still here.</span>
      <ol className={s.chain}>
        {succ.chain.map((n, i) => {
          const isSucc = i === last;
          const gone = i === 0 || (!isSucc && !!n.left && n.left <= asOf);
          const label = i === 0 ? `Left ${longDate(n.left)}` : isSucc ? "Still here" : gone ? `Also left ${longDate(n.left)}` : "Reports to";
          return (
            <li key={`${n.id}-${i}`} className={s.link}>
              {i > 0 && <span className={s.arrow} aria-hidden="true">→</span>}
              {isSucc ? (
                <div ref={dropRef} className={cx(s.chip, s.succ, drop !== "idle" && s.armed, drop === "over" && s.over)}>
                  <span className={s.chipLabel}>{label}</span>
                  <span className={s.chipName}>{n.name}</span>
                </div>
              ) : (
                <div className={cx(s.chip, gone && s.gone)}>
                  <span className={s.chipLabel}>{label}</span>
                  <span className={s.chipName}>{gone && <span className="sr-only">(left) </span>}{n.name}</span>
                </div>
              )}
              {isSucc && <p className={s.lineNote} aria-live="polite">{note}</p>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
