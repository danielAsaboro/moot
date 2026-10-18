"use client";
// Decision rot: moot decisions at each month end (GET /api/timeline). Every bar is one timeline point; choosing a
// bar time-travels the app to that month end. Thin bars in SVG; transparent buttons on top carry focus.
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { api, today } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAppState } from "@/lib/appState";
import { longDate } from "@/lib/format";
import { cx } from "@/components/ui";
import type { TimelinePoint } from "@/lib/types";
import s from "./ledger.module.css";

const H = 168, TOP = 22, PLOT = 112, BASE = TOP + PLOT, RIGHT = 22;

const moot = (p: TimelinePoint) => p.counts.MOOT ?? 0;
const monthYear = (iso: string) => longDate(iso).replace(/^\d+\s/, "");
const label = (p: TimelinePoint) =>
  `${monthYear(p.as_of)}: ${moot(p)} moot${p.newly_moot.length ? `, newly moot ${p.newly_moot.join(", ")}` : ""}`;

/** Tiny bar sparkline of the same series, for the Moot stat card. The bar for the current as-of month is solid. */
export function RotSpark({ points, asOf }: { points: TimelinePoint[]; asOf: string | null }) {
  const max = Math.max(1, ...points.map(moot));
  const matched = asOf ? points.findIndex(p => p.as_of.slice(0, 7) === asOf.slice(0, 7)) : -1;
  const sel = matched >= 0 ? matched : points.length - 1;
  return (
    <span className={s.spark} aria-hidden="true">
      {points.map((p, i) => (
        <span key={p.as_of} className={cx(s.sparkBar, i === sel && s.sparkOn, moot(p) === 0 && s.sparkZero, i > sel && s.sparkAfter)}
          style={{ height: `${Math.max(8, (moot(p) / max) * 100)}%` }} />
      ))}
    </span>
  );
}

export default function RotChart() {
  const { asOf, depth, setAsOf } = useAppState();
  const { data, error, loading } = useApi(() => api.timeline(depth), [depth]);
  const box = useRef<HTMLDivElement>(null);
  const btns = useRef<(HTMLButtonElement | null)[]>([]);
  const [w, setW] = useState(0);
  const [hot, setHot] = useState<number | null>(null);
  const [focusIdx, setFocusIdx] = useState<number | null>(null);
  const pid = useId().replace(/:/g, "");

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.floor(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [data]);

  const pts = data?.points ?? [];
  const n = pts.length;
  const matched = asOf ? pts.findIndex(p => p.as_of.slice(0, 7) === asOf.slice(0, 7)) : -1;
  const sel = matched >= 0 ? matched : n - 1;
  const first = pts.find(p => moot(p) > 0);
  const max = Math.max(1, ...pts.map(moot));
  const slot = n ? (w - RIGHT) / n : 0;
  const bw = Math.max(2, Math.min(14, slot * 0.5));
  const cxAt = (i: number) => i * slot + slot / 2;
  const h = (m: number) => (m / max) * PLOT;
  const tab = focusIdx ?? sel;
  const shown = pts[hot ?? sel];

  const travel = (p: TimelinePoint) => setAsOf(p.as_of >= today() ? null : p.as_of);

  const onKey = (e: KeyboardEvent, i: number) => {
    const to = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : null;
    if (to === null) return;
    e.preventDefault();
    btns.current[Math.max(0, Math.min(n - 1, to))]?.focus();
  };

  return (
    <section className={s.rot} aria-labelledby={`${pid}-t`}>
      <h3 id={`${pid}-t`} className="sr-only">Moot decisions at each month end</h3>
      <p className={cx("t-callout", s.rotLead)}>
        {shown ? <>
          <span className="lead-in">{moot(shown)} moot by {monthYear(shown.as_of)}.</span>{" "}
          {shown.newly_moot.length
            ? <>Newly moot that month: {shown.newly_moot.map((id, i) => <span key={id}>{i ? ", " : ""}<span className="id">{id}</span></span>)}.</>
            : first ? <>The first reason expired in {monthYear(first.as_of)}.</> : <>No reason has expired yet.</>}
        </> : " "}
      </p>

      {error ? <p className="t-footnote">The timeline could not load. {error}</p>
        : !data ? <div className={cx("skeleton", s.rotSkel)} aria-hidden />
        : !n ? <p className="t-footnote">No timeline points were returned.</p>
        : (
          <div className={s.rotCard}>
          <div ref={box} className={cx(s.rotPlot, loading && s.busy)} style={{ height: H }} aria-busy={loading}>
            {w > 0 && (
              <svg width={w} height={H} viewBox={`0 0 ${w} ${H}`} aria-hidden focusable="false" className={s.rotSvg}>
                <line x1={0} x2={w - RIGHT + 6} y1={TOP} y2={TOP} className={s.grid} />
                <text x={w} y={TOP + 4} textAnchor="end" className={s.axis}>{max}</text>
                <text x={w} y={BASE + 4} textAnchor="end" className={s.axis}>0</text>
                {pts.map((p, i) => {
                  const m = moot(p), bh = Math.max(2, h(m));
                  const yearMark = i === 0 || p.as_of.slice(5, 7) === "01";
                  return (
                    <g key={p.as_of}>
                      {hot === i && <rect x={i * slot + 1} y={TOP} width={slot - 2} height={PLOT} rx={4} className={s.hotBand} />}
                      <rect x={cxAt(i) - bw / 2} y={BASE - bh} width={bw} height={bh} rx={Math.min(3, bw / 2)}
                        className={cx(s.bar, m === 0 && s.barZero, i === sel && s.barOn, i > sel && s.barAfter)} />
                      {i === sel && <text x={cxAt(i)} y={BASE - bh - 6} textAnchor="middle" className={s.selNum}>{m}</text>}
                      {yearMark && <text x={i * slot + 1} y={BASE + 20} className={s.axis}>{p.as_of.slice(0, 4)}</text>}
                    </g>
                  );
                })}
                <line x1={0} x2={w - RIGHT + 6} y1={BASE + 0.5} y2={BASE + 0.5} className={s.baseline} />
              </svg>
            )}
            <div className={s.rotHits} role="group" aria-label="Months. Choose one to see the ledger as of that month end">
              {w > 0 && pts.map((p, i) => (
                <button key={p.as_of} ref={el => { btns.current[i] = el; }} type="button" className={s.hit}
                  style={{ left: i * slot, width: slot, top: TOP - 4, height: PLOT + 8 }}
                  tabIndex={i === tab ? 0 : -1} aria-pressed={i === sel} aria-label={label(p)}
                  onClick={() => travel(p)} onKeyDown={e => onKey(e, i)}
                  onMouseEnter={() => setHot(i)} onMouseLeave={() => setHot(null)}
                  onFocus={() => { setHot(i); setFocusIdx(i); }} onBlur={() => setHot(null)} />
              ))}
            </div>
          </div>
          </div>
        )}
      <p className="t-footnote" style={{ margin: 0 }}>Moot decisions at each month end, depth {data?.depth ?? depth}. Choose a month to see the ledger as it stood.</p>
    </section>
  );
}
