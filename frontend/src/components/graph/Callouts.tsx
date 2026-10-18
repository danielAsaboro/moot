"use client";
// Callouts: numbered markers on hairline leaders, each citing the id, its state or relation and the date from the rows.
// Plain HTML over the canvas so the text stays crisp; placed greedily so labels avoid each other and the parts.
// Sentence case; mono only for the id.
import { useMemo, useSyncExternalStore } from "react";
import type { Audit } from "@/lib/types";
import { STATE_WORD, VERDICT_WORD, cx } from "@/components/ui";
import { longDate } from "@/lib/format";
import { truncate, type Drawing, type Part } from "./layout";
import type { ProjStore, Projection } from "./store";
import s from "./IsoGraph.module.css";

interface Box { x: number; y: number; w: number; h: number }
interface Placed { part: Part; ax: number; ay: number; ex: number; ey: number; hx: number; box: Box; side: 1 | -1 }

const CH_ID = 6.9;   // mono 11.5px, average advance
const CH_SANS = 6.6; // sans 12.5px, average advance (the word is semibold)

/** What a part says: its id, one word (state, verdict or relation and date) and its text. */
export interface PartText { id: string; word: string; title: string }

export function partText(p: Part, audit: Audit): PartText {
  if (p.kind === "decision") return { id: p.id, word: VERDICT_WORD[audit.verdict], title: audit.decision.title };
  if (p.kind === "premise") return { id: p.id, word: p.state ? STATE_WORD[p.state] : "", title: p.premise?.text ?? "" };
  const e = p.evidence!;
  const rel = e.rel === "CONTRADICTS" ? "Contradicts" : "Supports";
  return { id: e.id, word: `${e.ruling ? "Ruling, " + rel.toLowerCase() : rel} · ${longDate(e.at)}`, title: e.title };
}

/** A callout's two lines. A long evidence id moves the date down to the second line so the label stays narrow. */
function calloutParts(p: Part, audit: Audit): { id: string; word: string; title: string } {
  const t = partText(p, audit);
  if (p.kind === "evidence" && t.id.length + t.word.length > 32) {
    const [rel, date] = t.word.split(" · ");
    return { id: t.id, word: rel, title: `${date} · ${t.title}` };
  }
  return t;
}

/** Kept for callers of the older name: the two lines of a callout as plain text. */
export function calloutLines(p: Part, audit: Audit): [string, string] {
  const t = partText(p, audit);
  return [`${t.id} · ${t.word}`, t.title];
}

function overlap(a: Box, b: Box) {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
  const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
  return w > 0 && h > 0 ? w * h : 0;
}

type Seg = [number, number, number, number];
function cross(a: Seg, b: Seg): boolean {
  const d = (p: number[], q: number[], r: number[]) => (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
  const p1 = [a[0], a[1]], p2 = [a[2], a[3]], p3 = [b[0], b[1]], p4 = [b[2], b[3]];
  return d(p1, p2, p3) * d(p1, p2, p4) < 0 && d(p3, p4, p1) * d(p3, p4, p2) < 0;
}

function place(parts: Part[], proj: Projection, audit: Audit, compact: boolean, mode: Mode): Placed[] {
  const { w: W, h: H, zoom } = proj;
  const cxm = W / 2;
  // The parts themselves are obstacles: a label should never sit on a tile.
  const obstacles: (Box & { key: string })[] = [];
  for (const p of parts) {
    const pt = proj.pts[p.key]; if (!pt) continue;
    const hw = (p.kind === "decision" ? 2.1 : 1.05) * zoom, hh = (p.kind === "decision" ? 1.5 : 0.7) * zoom;
    obstacles.push({ key: p.key, x: pt[0] - hw, y: pt[1] - hh * 0.8, w: hw * 2, h: hh * 1.7 });
  }
  if (!compact && mode.rings) for (const [k, pt] of Object.entries(proj.pts)) if (k.startsWith("ring:")) obstacles.push({ key: k, x: pt[0], y: pt[1] - 12, w: 70, h: 14 });
  const inBox = (x: number, y: number, b: Box) => x > b.x && x < b.x + b.w && y > b.y && y < b.y + b.h;
  // How many sample points of a leader land on other parts or on labels already placed.
  const crossings = (key: string, x0: number, y0: number, x1: number, y1: number) => {
    let n = 0;
    for (let i = 1; i <= 8; i++) {
      const x = x0 + ((x1 - x0) * i) / 8, y = y0 + ((y1 - y0) * i) / 8;
      for (const o of obstacles) if (o.key !== key && inBox(x, y, o)) n++;
      for (const q of placed) if (inBox(x, y, q.box)) n += 2;
    }
    return n;
  };
  const placed: Placed[] = [];
  // Cables, as drawn on screen: a leader should not cut across them.
  const cables: Seg[] = [];
  for (const p of parts) {
    const a = proj.pts[p.key], b = p.parent ? proj.pts[p.parent] : null;
    if (a && b) cables.push([a[0], a[1], b[0], b[1]]);
  }
  const order = [...parts].filter(p => !mode.only || mode.only.has(p.key))
    .sort((a, b) => (a.kind === "decision" ? -1 : b.kind === "decision" ? 1 : 0));
  const marker = mode.plain ? 12 : 30;
  for (const p of order) {
    const pt = proj.pts[p.key]; if (!pt) continue;
    const [ax, ay] = pt;
    const t = calloutParts(p, audit);
    const l1w = t.id.length * CH_ID + (t.word ? (t.word.length + 3) * CH_SANS : 0);
    const bw = compact ? (p.kind === "decision" ? p.id.length * CH_ID + 16 : 24)
      : Math.min(mode.oneLine ? 280 : 320, Math.max(l1w, mode.oneLine ? 0 : Math.min(truncate(t.title, 38).length * CH_SANS, 220)) + marker + 10);
    const bh = compact || mode.oneLine ? 22 : 36;
    const pref: 1 | -1 = ax >= cxm ? 1 : -1;
    let best: { score: number; c: Placed } | null = null;
    for (const dy of [-1, 1]) for (const sx of [pref, -pref] as (1 | -1)[]) for (const k of [1, 1.6, 2.3, 3.1, 4, 5]) {
      const ex = ax + sx * 18 * k, ey = ay + dy * (compact ? 20 : 26) * k;
      const hx = ex + sx * 12;
      const box: Box = { x: sx > 0 ? hx : hx - bw, y: ey - bh / 2, w: bw, h: bh };
      let score = k * 40 + (dy > 0 ? 25 : 0) + (sx !== pref ? 30 : 0);
      const out = Math.max(0, -box.x) + Math.max(0, box.x + box.w - W) + Math.max(0, -box.y) + Math.max(0, box.y + box.h - H);
      score += out * 400;
      for (const q of placed) score += overlap(box, q.box) * 6;
      for (const o of obstacles) score += overlap(box, o) * 6;
      for (const c of cables) for (let i = 1; i < 12; i++) if (inBox(c[0] + ((c[2] - c[0]) * i) / 12, c[1] + ((c[3] - c[1]) * i) / 12, box)) score += 90;
      score += crossings(p.key, ax, ay, ex, ey) * 120 + crossings(p.key, ex, ey, hx, ey) * 120;
      const legs: Seg[] = [[ax, ay, ex, ey], [ex, ey, hx, ey]];
      for (const l of legs) {
        for (const q of placed) if (cross(l, [q.ax, q.ay, q.ex, q.ey]) || cross(l, [q.ex, q.ey, q.hx, q.ey])) score += 2500;
        for (const c of cables) if (cross(l, c)) score += 160;
      }
      if (!best || score < best.score) best = { score, c: { part: p, ax, ay, ex, ey, hx, box, side: sx } };
    }
    if (best) placed.push(best.c);
  }
  return placed;
}

/** How the callouts are drawn: `only` limits them to some parts, `plain` drops the numbers (no parts list to match),
 *  `oneLine` drops the text line, `rings` shows the hop labels. */
export interface Mode { only?: Set<string> | null; plain?: boolean; oneLine?: boolean; rings?: boolean }
const FULL: Mode = { rings: true };

export default function Callouts({ store, parts, drawing, audit, compact, active, onHover, mode = FULL }: {
  store: ProjStore; parts: Part[]; drawing: Drawing; audit: Audit; compact: boolean;
  active: Set<string> | null; onHover: (key: string | null) => void; mode?: Mode;
}) {
  const proj = useSyncExternalStore(store.subscribe, store.get, () => null);
  const placed = useMemo(() => (proj ? place(parts, proj, audit, compact, mode) : []), [proj, parts, audit, compact, mode]);
  if (!proj) return null;
  const faded = (k: string) => !!active && !active.has(k);
  const tone = (p: Part) => (p.kind === "evidence" ? (p.rel === "CONTRADICTS" ? s.tAccent : s.tHolds)
    : p.kind === "premise" ? (p.state === "expired" ? s.tAccent : p.state === "disputed" ? s.tDisputed : p.state === "holds" ? "" : s.tMuted) : "");

  return (
    <div className={s.overlay} aria-hidden="true">
      <svg className={s.leaders} width={proj.w} height={proj.h} viewBox={`0 0 ${proj.w} ${proj.h}`}>
        {placed.map(c => (
          <g key={c.part.key} className={cx(faded(c.part.key) && s.faded)}>
            <circle cx={c.ax} cy={c.ay} r={2.2} />
            <polyline points={`${c.ax},${c.ay} ${c.ex},${c.ey} ${c.hx},${c.ey}`} />
          </g>
        ))}
      </svg>
      {!compact && mode.rings && drawing.rings.map(r => {
        const pt = proj.pts[`ring:${r.label}`];
        const word = r.label[0].toUpperCase() + r.label.slice(1);
        const hidden = pt && placed.some(c => overlap(c.box, { x: pt[0] + 4, y: pt[1] - 8, w: word.length * 7 + 6, h: 14 }) > 0);
        return pt && !hidden && <span key={r.label} className={s.ringLabel} style={{ left: pt[0] + 6, top: pt[1] - 6 }}>{word}</span>;
      })}
      {placed.map(c => {
        const t = calloutParts(c.part, audit);
        return (
          <div key={c.part.key} className={cx(s.callout, c.side < 0 && s.left, compact && s.compact, faded(c.part.key) && s.faded)}
            style={{ left: c.box.x, top: c.box.y, width: c.box.w }}
            onMouseEnter={() => onHover(c.part.key)} onMouseLeave={() => onHover(null)}>
            {mode.plain ? null : c.part.num ? <span className={s.num}>{c.part.num}</span> : compact && <span className={s.numD}>{c.part.id}</span>}
            {!compact && (
              <span className={s.ctext}>
                <span className={s.cl1}><span className={s.cid}>{t.id}</span>{t.word && <span className={tone(c.part)}> · {t.word}</span>}</span>
                {!mode.oneLine && <span className={s.cl2}>{truncate(t.title, 38)}</span>}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
