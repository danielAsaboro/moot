"use client";
// A decision id on a small badge hanging from a lanyard. Drag it onto the successor's chip to propose a handover.
// Pointer events only; a spring swings the badge while it moves and settles it on release. Nothing is written here:
// a drop only asks the page to open its confirmation.
import { useEffect, useRef } from "react";
import s from "./orphans.module.css";

const HOOK = 7;         // the clip at the top of the lanyard, px
const ROPE = 18;        // resting lanyard length, px
const MAX_SWING = 22;   // degrees

interface Props {
  id: string;
  disabled?: boolean;
  /** Plain hint for the pointer tooltip, e.g. "Drag onto Kwame Boateng to hand over". */
  hint: string;
  getTarget: () => HTMLElement | null;
  onDragState: (state: "idle" | "dragging" | "over") => void;
  onDrop: () => void;
}

export default function LanyardBadge({ id, disabled, hint, getTarget, onDragState, onDrop }: Props) {
  const badge = useRef<HTMLDivElement>(null);
  const rope = useRef<SVGPathElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  // Mutable physics state; written to the DOM directly so a drag never re-renders React.
  const m = useRef({
    dragging: false, over: false, pointer: -1, sx: 0, sy: 0,
    x: 0, y: 0, vx: 0, vy: 0, px: 0, pv: 0, angle: 0, av: 0, raf: 0, reduced: false,
  });
  // Callbacks change identity on every parent render; keep the latest without restarting anything.
  const cb = useRef({ getTarget, onDragState, onDrop });
  useEffect(() => { cb.current = { getTarget, onDragState, onDrop }; });

  useEffect(() => {
    const mq = matchMedia("(prefers-reduced-motion: reduce)");
    const set = () => { m.current.reduced = mq.matches; };
    set();
    mq.addEventListener("change", set);
    const st = m.current;
    return () => { mq.removeEventListener("change", set); cancelAnimationFrame(st.raf); };
  }, []);

  const paint = () => {
    const st = m.current;
    if (badge.current) badge.current.style.transform = `translate(${st.x}px, ${st.y}px) rotate(${st.angle}deg)`;
    if (rope.current) {
      const ex = st.x, ey = st.y + ROPE;
      const slack = Math.max(0, ROPE - Math.hypot(ex, ey));
      rope.current.setAttribute("d", `M0 0 Q ${ex / 2} ${ey / 2 + slack * 0.6} ${ex} ${ey}`);
    }
    wrap.current?.toggleAttribute("data-lifted", st.dragging || Math.abs(st.x) + Math.abs(st.y) > 1);
  };

  const step = () => {
    const st = m.current;
    if (st.dragging) {
      // follow the pointer exactly; swing from a smoothed horizontal speed
      st.pv = st.pv * 0.7 + (st.x - st.px) * 0.3;
      st.px = st.x;
      const target = st.reduced ? 0 : Math.max(-MAX_SWING, Math.min(MAX_SWING, st.pv * 1.6));
      st.av = (st.av + (target - st.angle) * 0.14) * 0.8;
      st.angle = st.reduced ? 0 : st.angle + st.av;
    } else {
      // spring home, swinging with the return speed, then settle
      st.vx = (st.vx - st.x * 0.12) * 0.78;
      st.vy = (st.vy - st.y * 0.12) * 0.78;
      st.x += st.vx; st.y += st.vy;
      const target = Math.max(-MAX_SWING, Math.min(MAX_SWING, st.vx * 1.4));
      st.av = (st.av + (target - st.angle) * 0.12) * 0.84;
      st.angle += st.av;
      const still = [st.x, st.y, st.vx, st.vy, st.angle, st.av].every(v => Math.abs(v) < 0.05);
      if (still) { st.x = st.y = st.vx = st.vy = st.angle = st.av = 0; paint(); st.raf = 0; return; }
    }
    paint();
    st.raf = requestAnimationFrame(step);
  };

  const kick = () => { if (!m.current.raf) m.current.raf = requestAnimationFrame(step); };

  const hit = (cx: number, cy: number) => {
    const t = cb.current.getTarget();
    if (!t) return false;
    const r = t.getBoundingClientRect();
    return cx >= r.left && cx <= r.right && cy >= r.top && cy <= r.bottom;
  };

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (disabled || (e.pointerType === "mouse" && e.button !== 0)) return;
    e.preventDefault();
    const st = m.current;
    e.currentTarget.setPointerCapture(e.pointerId);
    st.pointer = e.pointerId; st.dragging = true; st.over = false;
    st.sx = e.clientX - st.x; st.sy = e.clientY - st.y; st.px = st.x; st.pv = 0;
    cb.current.onDragState("dragging");
    kick();
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const st = m.current;
    if (!st.dragging || e.pointerId !== st.pointer) return;
    st.x = e.clientX - st.sx; st.y = e.clientY - st.sy;
    const over = hit(e.clientX, e.clientY);
    if (over !== st.over) { st.over = over; cb.current.onDragState(over ? "over" : "dragging"); }
    if (st.reduced) paint();
  };

  const release = (e: React.PointerEvent<HTMLDivElement>, drop: boolean) => {
    const st = m.current;
    if (!st.dragging || e.pointerId !== st.pointer) return;
    st.dragging = false; st.pointer = -1;
    const landed = drop && hit(e.clientX, e.clientY);
    st.over = false;
    cb.current.onDragState("idle");
    st.vx = st.pv; st.vy = 0;
    if (st.reduced) { st.x = st.y = st.vx = st.vy = st.angle = st.av = 0; paint(); }
    else kick();
    if (landed) cb.current.onDrop();
  };

  return (
    <div ref={wrap} className={s.lanyard} data-disabled={disabled || undefined}>
      <span className={s.hook} aria-hidden="true" />
      <svg className={s.rope} style={{ top: HOOK }} width="1" height="1" aria-hidden="true">
        <path ref={rope} d={`M0 0 L0 ${ROPE}`} />
      </svg>
      <div
        ref={badge}
        className={s.badge}
        style={{ top: HOOK + ROPE }}
        title={disabled ? undefined : hint}
        aria-hidden="true"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={e => release(e, true)}
        onPointerCancel={e => release(e, false)}
      >
        <span className={s.slot} />
        <span className={s.badgeLabel}>Decision</span>
        <span className={s.badgeId}>{id}</span>
      </div>
    </div>
  );
}
