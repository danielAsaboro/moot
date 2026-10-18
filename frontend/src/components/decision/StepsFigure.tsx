"use client";
// Fig. 1: the audit drawn as a quiet line-art outline. Each box is a row the API returned (the decision, a premise, a dated
// evidence edge); the step in view decides which boxes are drawn in ink and which are still ghosts.
import { useEffect, useRef, useState } from "react";
import type { Verdict } from "@/lib/types";
import { longDate } from "@/lib/format";
import { VERDICT_WORD, cx } from "@/components/ui";
import type { FigNode } from "./StepsModel";
import s from "./Steps.module.css";

const D = 6;                         // depth of the oblique extrusion
const H: Record<FigNode["kind"], number> = { decision: 50, premise: 46, superseded: 46, evidence: 38 };
const GAP = 12;
const STAMP_H = 66;

interface Placed extends FigNode { x: number; y: number; w: number; h: number }

function fit(text: string, px: number, charW: number): string {
  const n = Math.max(4, Math.floor(px / charW));
  return text.length <= n ? text : `${text.slice(0, n - 1).trimEnd()}…`;
}

export default function StepsFigure({ nodes, step, active, last, verdict, asOf, label }: {
  nodes: FigNode[]; step: number; active: Set<string>; last: number; verdict: Verdict; asOf: string; label: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(600);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const indent = W < 480 ? 14 : 28;
  let y = D + 10;
  const placed: Placed[] = nodes.map(n => {
    const x = 12 + n.level * indent;
    const full = W - x - D - 14;
    const w = n.kind === "evidence" ? Math.min(full, 360) : n.kind === "decision" ? full : Math.min(full, 520);
    const p = { ...n, x, y, w, h: H[n.kind] };
    y += p.h + GAP;
    return p;
  });
  const height = y + STAMP_H;
  const byKey = new Map(placed.map(p => [p.key, p]));
  const stampOn = step === last;
  const stampText = VERDICT_WORD[verdict];
  const sw = Math.round(Math.max(110, stampText.length * 12 + 36));
  const verdictTone = verdict === "MOOT" ? s.vMoot : verdict === "DISPUTED" ? s.vDisputed : verdict === "HOLDS" ? s.vHolds : s.vMuted;

  return (
    <div ref={ref} className={s.figWrap}>
      <svg className={s.fig} width={W} height={height} viewBox={`0 0 ${W} ${height}`} role="img" aria-label={label}>
        {/* connectors first, under the boxes */}
        {placed.map(n => {
          const p = n.parent ? byKey.get(n.parent) : null;
          if (!p) return null;
          const vx = p.x + 14, top = p.y + p.h, my = n.y + n.h / 2;
          const shown = n.step <= step;
          const ev = n.kind === "evidence";
          return (
            <g key={`c-${n.key}`} className={cx(s.wire, !shown && s.ghost, active.has(n.key) && s.wireOn, ev && s.wireEv,
              ev && n.tone === "accent" && n.step <= step && s.wireContra)}>
              <path d={`M${vx} ${top} V${my} H${n.x}`} />
              {ev
                ? <path className={s.head} d={`M${vx - 3.5} ${top + 6} L${vx} ${top + 1} L${vx + 3.5} ${top + 6} Z`} />
                : <path className={s.head} d={`M${n.x - 6} ${my - 3.5} L${n.x - 1} ${my} L${n.x - 6} ${my + 3.5} Z`} />}
            </g>
          );
        })}
        {placed.map(n => <Box key={n.key} n={n} step={step} on={active.has(n.key)} />)}
        {/* the verdict stamp, inked on the last step */}
        <g className={cx(s.stamp, !stampOn && s.ghost, stampOn && verdictTone)} transform={`translate(12 ${y + 6})`}>
          <path className={s.bracket} d={`M0 12 V0 H12 M${sw - 12} 0 H${sw} V12 M${sw} 40 V52 H${sw - 12} M12 52 H0 V40`} />
          <text x={sw / 2} y={34} textAnchor="middle" className={s.stampText}>{stampOn ? stampText : "?"}</text>
          <text x={sw + 14} y={22} className={s.stampMeta}>Verdict</text>
          <text x={sw + 14} y={38} className={s.stampMeta}>As of {longDate(asOf)}</text>
        </g>
      </svg>
    </div>
  );
}

function Box({ n, step, on }: { n: Placed; step: number; on: boolean }) {
  const { x, y, w, h } = n;
  const shown = n.step <= step;
  const tagShown = n.tagStep <= step;
  const tone = tagShown ? n.tone : null;
  const big = n.kind === "decision";
  const titlePx = big ? 13.5 : n.kind === "evidence" ? 12 : 12.5;
  const tagW = n.tag.length * 6 + 8;
  return (
    <g className={cx(s.box, !shown && s.ghost, on && s.on, tone === "accent" && s.tAccent, tone === "holds" && s.tHolds,
      tone === "disputed" && s.tDisputed, n.kind === "evidence" && s.ev)}>
      <title>{`${n.id}: ${n.title}`}</title>
      <path className={s.top} d={`M${x} ${y} L${x + D} ${y - D} H${x + w + D} L${x + w} ${y} Z`} />
      <path className={s.side} d={`M${x + w} ${y} L${x + w + D} ${y - D} V${y + h - D} L${x + w} ${y + h} Z`} />
      <rect className={s.face} x={x} y={y} width={w} height={h} />
      <text x={x + 10} y={y + 16} className={s.id}>{fit(n.id, w - tagW - 20, 6.4)}</text>
      {tagShown && <text x={x + w - 10} y={y + 16} textAnchor="end" className={s.tag}>{n.tag}</text>}
      <text x={x + 10} y={y + (big ? 37 : n.kind === "evidence" ? 31 : 35)} className={s.title} style={{ fontSize: titlePx }}>
        {fit(n.title, w - 20, titlePx * 0.52)}
      </text>
    </g>
  );
}
