"use client";
// The rows behind one verdict as soft chips: the decision, each reason on the path (indented by step), and the dated
// evidence that decided it. It builds one step at a time as it scrolls into view. Everything comes from the response.
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { DecisionResponse, EvidenceEvent, PathNode, Premise } from "@/lib/types";
import { StateTag, decidingEvent, cx } from "@/components/ui";
import { longDate } from "@/lib/format";
import s from "./HowRecords.module.css";

const STEP_MS = 350;

/** The premise whose deciding event is a contradiction, deepest first; else the first premise with evidence. */
export function pickPremise(premises: Premise[]): { premise: Premise; event: EvidenceEvent | null } | null {
  const scored = premises.map(p => ({ premise: p, event: decidingEvent(p.evidence) }));
  const contra = scored.filter(x => x.event?.rel === "CONTRADICTS").sort((a, b) => b.premise.hops - a.premise.hops);
  return contra[0] ?? scored.find(x => x.event) ?? scored[0] ?? null;
}

const relation = (from: PathNode) => (from.label === "Decision" ? "because of" : "which rests on");
const kindWord = (n: PathNode, k: number) => (n.label === "Decision" ? "Decision" : k > 1 ? "The reason behind it" : "Reason");

/** Reveal `n` steps one at a time once `ref` scrolls into view (all at once with reduced motion). */
function useSteps(n: number) {
  const ref = useRef<HTMLOListElement>(null);
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el || n === 0) return;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || typeof IntersectionObserver === "undefined") { setShown(n); return; }
    let timer: ReturnType<typeof setInterval> | undefined;
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      io.disconnect();
      setShown(1);
      timer = setInterval(() => setShown(k => {
        if (k + 1 >= n) clearInterval(timer);
        return Math.min(n, k + 1);
      }), STEP_MS);
    }, { threshold: 0.3 });
    io.observe(el);
    return () => { io.disconnect(); if (timer) clearInterval(timer); };
  }, [n]);
  return { ref, shown };
}

export default function HeroRecords({ data, error, asOf, depth }: { data: DecisionResponse | null; error: string | null; asOf: string; depth: number }) {
  const audit = data?.audit;
  const pick = audit ? pickPremise(audit.premises) : null;
  const path = audit ? (pick?.premise.path ?? [{ id: audit.decision.id, label: "Decision", title: audit.decision.title }]) : [];
  const ev = pick?.event ?? null;
  const { ref, shown } = useSteps(path.length + (ev ? 1 : 0));

  if (error) return <div className={s.records}><p className="t-sub">The rows behind this verdict could not load. {error}</p></div>;
  if (!audit) {
    return (
      <div className={s.records} aria-busy="true" aria-label="Loading the rows behind one verdict">
        {[0, 1, 2, 3].map(i => <span key={i} className={`skeleton ${s.skel}`} style={{ ["--k" as string]: i }} />)}
      </div>
    );
  }

  const stateOf = (id: string) => audit.premises.find(p => p.id === id)?.state;
  const contra = ev?.rel === "CONTRADICTS";

  return (
    <div className={s.records}>
      <ol ref={ref} className={s.chain} aria-label={`Evidence path for ${audit.decision.id}`}>
        {path.map((n, k) => {
          const st = n.label === "Premise" ? stateOf(n.id) : undefined;
          return (
            <li key={n.id} className={cx(s.step, k < shown && s.on)} style={{ ["--k" as string]: Math.min(k, 3) }}>
              {k > 0 && <span className={s.rel}>{relation(path[k - 1])}</span>}
              <div className={cx(s.chip, n.label === "Decision" && s.decision)}>
                <span className={s.meta}>
                  <span>{kindWord(n, k)}</span>
                  <span className="id">{n.id}</span>
                  {n.label === "Decision" && <span className={s.faint}>decided {longDate(audit.decision.decided_on)}</span>}
                  {st && <span className={s.tag}><StateTag state={st} /></span>}
                </span>
                <span className={s.text}>{n.title}</span>
              </div>
            </li>
          );
        })}
        {ev && (
          <li className={cx(s.step, s.evidence, path.length < shown && s.on)} style={{ ["--k" as string]: Math.min(path.length, 3) }}>
            <span className={cx(s.rel, contra && s.relContra)}>
              {contra ? "contradicted by" : "supported by"} <span className="id">{ev.id}</span> on {longDate(ev.at)}
            </span>
            <div className={cx(s.chip, contra ? s.contra : s.support)}>
              <span className={s.meta}>
                <span>Evidence</span><span className={s.faint}>{ev.kind === "pr" ? "pull request" : ev.kind}</span>
              </span>
              <span className={s.text}>{ev.title}</span>
            </div>
          </li>
        )}
      </ol>
      <p className={s.foot}>
        <Link className="link" href={`/app/?d=${encodeURIComponent(audit.decision.id)}&as_of=${asOf}&depth=${depth}`}>
          Open {audit.decision.id} in the ledger ›
        </Link>
      </p>
    </div>
  );
}
