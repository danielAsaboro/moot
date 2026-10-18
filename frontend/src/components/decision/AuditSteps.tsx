"use client";
// The Steps tab: "Fig. 1", the audit walked one hop at a time, with a row of numbered steps and a caption per step.
// Every caption is built from the rows (StepsModel); the figure inks in the rows each step adds.
import { useMemo, useState, type KeyboardEvent } from "react";
import type { Audit } from "@/lib/types";
import { cx } from "@/components/ui";
import { longDate } from "@/lib/format";
import { buildSteps } from "./StepsModel";
import StepsFigure from "./StepsFigure";
import s from "./Steps.module.css";

export default function AuditSteps({ audit }: { audit: Audit }) {
  const { nodes, steps } = useMemo(() => buildSteps(audit), [audit]);
  const last = steps.length - 1;
  // The walkthrough restarts at the first step whenever the decision, the date or the depth changes.
  const viewKey = `${audit.decision.id}|${audit.as_of}|${audit.depth}`;
  const [pos, setPos] = useState({ key: viewKey, i: 0 });
  const cur = Math.min(pos.key === viewKey ? pos.i : 0, last);
  const go = (i: number) => setPos({ key: viewKey, i: Math.max(0, Math.min(last, i)) });
  const onKey = (e: KeyboardEvent) => {
    if ((e.target as HTMLElement).closest("input, textarea, select")) return;
    if (e.key === "ArrowRight") { e.preventDefault(); go(cur + 1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); go(cur - 1); }
    else if (e.key === "Home") { e.preventDefault(); go(0); }
    else if (e.key === "End") { e.preventDefault(); go(last); }
  };
  const active = useMemo(() => new Set(steps[cur]?.adds ?? []), [steps, cur]);
  const hops = `${audit.depth} ${audit.depth === 1 ? "hop" : "hops"} deep`;
  const figLabel = `Figure 1: ${audit.decision.id} as of ${longDate(audit.as_of)}, ${hops}`;
  const st = steps[cur];
  const [first, ...rest] = st.sentences;

  return (
    <section className={s.root} aria-label={`How the verdict on ${audit.decision.id} was reached`} onKeyDown={onKey}>
      <div className={s.head}>
        <p className="t-footnote">Fig. 1 · <span className="id">{audit.decision.id}</span> as of {longDate(audit.as_of)}, {hops}</p>
        <p className="t-footnote">Step {cur + 1} of {steps.length}</p>
      </div>

      <div className={s.figure} tabIndex={0} aria-label={`${figLabel}. Use the left and right arrow keys to step through.`}>
        <StepsFigure nodes={nodes} step={cur} active={active} last={last} verdict={audit.verdict} asOf={audit.as_of} label={figLabel} />
      </div>

      <ol className={s.stops} aria-label="Steps">
        {steps.map((x, i) => (
          <li key={i} className={cx(s.stop, i < cur && s.past, i === cur && s.now)}>
            <button type="button" onClick={() => go(i)} aria-current={i === cur ? "step" : undefined} aria-label={`Step ${i + 1}: ${x.title}`}>
              <span className={s.dot} aria-hidden="true">{i + 1}</span>
              <span className={s.stopLabel} aria-hidden="true">{x.short}</span>
            </button>
          </li>
        ))}
      </ol>

      <div className={s.caption} aria-live="polite">
        <p className={s.capLead}><span className="lead-in">{st.title}.</span> {first}</p>
        {rest.map((t, i) => <p key={i} className={s.capMore}>{t}</p>)}
      </div>

      <div className={s.nav}>
        <button type="button" className="btn ghost small" onClick={() => go(cur - 1)} disabled={cur === 0}>Previous</button>
        <span className={cx("t-footnote", s.keys)}>Or use the arrow keys.</span>
        <button type="button" className="btn small" onClick={() => go(cur + 1)} disabled={cur === last}>Next</button>
      </div>
    </section>
  );
}
