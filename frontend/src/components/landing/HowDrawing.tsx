"use client";
// Line drawing of one real audit on the red band: the decision box, its reasons indented by step, the evidence that
// decides each reason, and the other decisions that rest on a broken reason (from `impact`). Every box is a row from the
// response; nothing is drawn that the API did not return. Wide: the other decisions sit in a side column. Narrow: below.
import type { ReactNode } from "react";
import type { Audit, EvidenceEvent, Impact, Premise } from "@/lib/types";
import { STATE_WORD, cx, decidingEvent } from "@/components/ui";
import { longDate } from "@/lib/format";
import s from "./BlastRadius.module.css";

const NARROW = 440;     // viewBox width on small screens
const WIDE = 640;       // and with room for a side column
const TOP = 34;         // first row's front-face top (room for the isometric top face)
const ROW = 104;         // row pitch
const H = 68;           // front-face height
const INDENT = 40;      // x step per hop
const DX = 12, DY = 9;  // isometric depth offset
const MARGIN = 14;
const LANES = 44;       // narrow: room on the right for the lines from the other decisions

interface Box {
  key: string; x: number; y: number; w: number; tag: ReactNode; lines: string[];
  marked?: boolean; dashed?: boolean; faint?: boolean;
}
interface Edge { d: string; label: string; lx: number; ly: number; marked?: boolean; arrow?: boolean; faint?: boolean; end?: boolean }

function wrap(text: string, max: number, keep = 2): string[] {
  const out: string[] = [];
  let cur = "";
  for (const word of text.split(/\s+/)) {
    const next = cur ? `${cur} ${word}` : word;
    if (next.length > max && cur) { out.push(cur); cur = word; } else cur = next;
  }
  if (cur) out.push(cur);
  if (out.length <= keep) return out;
  const kept = out.slice(0, keep);
  kept[keep - 1] = `${kept[keep - 1]}…`;
  return kept;
}

const charsFor = (w: number) => Math.floor((w - 20) / 7.7);
const broken = (p?: Premise) => Boolean(p && (p.state === "expired" || p.state === "disputed"));
const Id = ({ children }: { children: string }) => <tspan className={s.tagId}>{children}</tspan>;

function IsoBox({ b }: { b: Box }) {
  const { x, y, w } = b;
  const top = `M${x},${y} L${x + DX},${y - DY} L${x + w + DX},${y - DY} L${x + w},${y} Z`;
  const side = `M${x + w},${y} L${x + w + DX},${y - DY} L${x + w + DX},${y + H - DY} L${x + w},${y + H} Z`;
  return (
    <g className={cx(s.box, b.marked && s.marked, b.dashed && s.dashed, b.faint && s.faint)}>
      <path d={top} className={s.face} />
      <path d={side} className={s.face} />
      <rect x={x} y={y} width={w} height={H} className={s.front} />
      <text x={x + 11} y={y + 20} className={s.tag}>{b.tag}</text>
      {b.lines.map((l, i) => <text key={i} x={x + 11} y={y + 41 + i * 18} className={s.boxTitle}>{l}</text>)}
    </g>
  );
}

export default function HowDrawing({ audit, impact = [], wide = false }: { audit: Audit; impact?: Impact[]; wide?: boolean }) {
  const W = wide ? WIDE : NARROW;
  const premises: Premise[] = [...audit.premises].sort((a, b) => a.hops - b.hops);

  // Other decisions resting on a broken reason, at most three, each with the reason box it hangs from.
  const also: { id: string; title: string; premise: string }[] = [];
  for (const im of impact) {
    if (!broken(premises.find(x => x.id === im.premise.id))) continue;
    for (const d of im.decisions) {
      if (d.id === audit.decision.id || also.some(a => a.id === d.id) || also.length >= 3) continue;
      also.push({ id: d.id, title: d.title, premise: im.premise.id });
    }
  }
  // Narrow with a fan-out: keep a lane gutter on the right so the lines never cross a box.
  const right = !wide && also.length ? W - MARGIN - LANES : W - MARGIN;

  const boxes: Box[] = [];
  const edges: Edge[] = [];
  const at = new Map<string, Box>();

  let row = 0;
  const dw = Math.min(300, right - MARGIN - DX - 60);
  const dec: Box = {
    key: audit.decision.id, x: MARGIN, y: TOP, w: dw,
    tag: <>Decision <Id>{audit.decision.id}</Id></>, lines: wrap(audit.decision.title, charsFor(dw)),
  };
  boxes.push(dec);
  at.set(dec.key, dec);

  for (const p of premises) {
    row += 1;
    const x = MARGIN + Math.min(p.hops, 4) * INDENT;
    const w = Math.min(270, right - DX - x);
    const box: Box = {
      key: p.id, x, y: TOP + row * ROW, w, dashed: p.state === "expired",
      tag: `${p.hops > 1 ? "The reason behind it" : "Reason"} · ${STATE_WORD[p.state].toLowerCase()}`,
      lines: wrap(p.text, charsFor(w)),
    };
    boxes.push(box);
    at.set(p.id, box);

    // structural edge from the node before it on its path (decision or the premise it derives from)
    const parentId = p.path.length > 1 ? p.path[p.path.length - 2].id : audit.decision.id;
    const parent = at.get(parentId) ?? dec;
    const spine = parent.x + 20;
    edges.push({
      d: `M${spine},${parent.y + H} V${box.y + H / 2} H${box.x}`,
      label: parent === dec ? "because of" : "rests on",
      lx: spine + 8, ly: parent.y + H + 19,
    });

    const ev: EvidenceEvent | null = decidingEvent(p.evidence);
    if (ev) {
      row += 1;
      const ew = Math.min(232, right - MARGIN - DX);
      const ex = wide ? Math.min(box.x + 120, right - DX - ew) : right - DX - ew;
      const marked = ev.rel === "CONTRADICTS" && broken(p);
      const eb: Box = {
        key: `${p.id}:${ev.id}`, x: ex, y: TOP + row * ROW, w: ew, marked,
        tag: <>Evidence <Id>{ev.id}</Id></>, lines: wrap(ev.title, charsFor(ew)),
      };
      boxes.push(eb);
      const lo = Math.max(box.x, eb.x), hi = Math.min(box.x + box.w, eb.x + eb.w);
      const lx = hi > lo ? Math.round(lo + (hi - lo) * 0.62) : eb.x + 30;
      edges.push({
        d: `M${lx},${eb.y - DY / 2} V${box.y + H + 2}`,
        label: `${ev.rel === "CONTRADICTS" ? "contradicted" : "supported"} on ${longDate(ev.at)}`,
        // narrow with a fan-out: the label sits left of the arrow so it stays clear of the lanes on the right
        ...(!wide && also.length ? { lx: lx - 8, end: true } : { lx: lx + 8 }), ly: box.y + H + 22, marked, arrow: true,
      });
    }
  }

  also.forEach((a, k) => {
    const target = at.get(a.premise);
    if (!target) return;
    const tag = <>Also rests on it <Id>{a.id}</Id></>;
    if (wide) {
      const iw = 184, ix = W - MARGIN - DX - iw;
      const ib: Box = { key: `also:${a.id}`, x: ix, y: TOP + k * ROW * 0.82, w: iw, faint: true, tag, lines: wrap(a.title, charsFor(iw)) };
      boxes.push(ib);
      const jx = ix - 22 - k * 12;
      const ty = target.y + 16 + k * 12;
      edges.push({
        d: `M${ix},${ib.y + H / 2} H${jx} V${ty} H${target.x + target.w + DX / 2}`,
        label: k === 0 ? "because of" : "", lx: jx - 60, ly: ib.y + H / 2 - 6, arrow: true, faint: true,
      });
    } else {
      // stacked under the drawing; each line runs up its own lane and enters the reason's side face, later ones higher
      row += 1;
      const iw = Math.min(232, right - MARGIN - DX), ix = right - DX - iw;
      const ib: Box = { key: `also:${a.id}`, x: ix, y: TOP + row * ROW, w: iw, faint: true, tag, lines: wrap(a.title, charsFor(iw)) };
      boxes.push(ib);
      const lane = right + 12 + k * 12;
      const ty = target.y + H / 2 + 6 - k * 12;
      edges.push({
        d: `M${ix + iw + DX},${ib.y + H / 2 - DY / 2} H${lane} V${ty} H${target.x + target.w + DX + 2}`,
        label: "", lx: 0, ly: 0, arrow: true, faint: true,
      });
    }
  });

  const height = TOP + row * ROW + H + 20;
  const summary = premises.map(p => {
    const ev = decidingEvent(p.evidence);
    return `${p.text} (${STATE_WORD[p.state].toLowerCase()}${ev ? `, ${ev.rel === "CONTRADICTS" ? "contradicted" : "supported"} by ${ev.id} on ${longDate(ev.at)}` : ""})`;
  }).join("; ");
  const alsoText = also.length ? ` Also resting on the broken reason: ${also.map(a => `${a.id} ${a.title}`).join("; ")}.` : "";

  return (
    <svg viewBox={`0 0 ${W} ${height}`} className={s.drawing} role="img"
      aria-label={`${audit.decision.id} ${audit.decision.title}. Reasons: ${summary}.${alsoText}`}>
      <defs>
        <marker id="blast-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 Z" className={s.arrowHead} />
        </marker>
      </defs>
      {edges.map((e, i) => (
        <g key={i} className={cx(s.edge, e.marked && s.edgeMarked, e.faint && s.faint)}>
          <path d={e.d} markerEnd={e.arrow ? "url(#blast-arrow)" : undefined} />
          {e.label && <text x={e.lx} y={e.ly} textAnchor={e.end ? "end" : undefined} className={s.edgeLabel}>{e.label}</text>}
        </g>
      ))}
      {boxes.map(b => <IsoBox key={b.key} b={b} />)}
    </svg>
  );
}
