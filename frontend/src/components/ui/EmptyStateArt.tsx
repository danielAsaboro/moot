"use client";
// Isometric line drawings for EmptyState: one quiet machine, drawn differently per kind. Static SVG, no network.
import type { ReactElement } from "react";
import s from "./EmptyState.module.css";

export type EmptyKind = "not_in_graph" | "unknown_entity" | "nothing_selected" | "empty" | "error" | "loading";

type P3 = [number, number, number];
const U = 9;                       // px per unit
const C = Math.cos(Math.PI / 6);   // isometric x factor
const S = 0.5;                     // isometric y factor

function pr([x, y, z]: P3): [number, number] {
  return [(x - y) * C * U, (x + y) * S * U - z * U];
}
const pts = (ps: P3[]) => ps.map(p => pr(p).map(n => n.toFixed(1)).join(",")).join(" ");

/** The three visible faces of an axis-aligned box: top, front-left (y = y1) and front-right (x = x1). */
function Box({ a, b, cls }: { a: P3; b: P3; cls?: string }) {
  const [x0, y0, z0] = a; const [x1, y1, z1] = b;
  return (
    <g className={cls}>
      <polygon className={s.faceL} points={pts([[x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]])} />
      <polygon className={s.faceR} points={pts([[x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]])} />
      <polygon className={s.faceT} points={pts([[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]])} />
    </g>
  );
}

function Line({ a, b, className }: { a: P3; b: P3; className?: string }) {
  const [x1, y1] = pr(a); const [x2, y2] = pr(b);
  return <line className={className} x1={x1} y1={y1} x2={x2} y2={y2} />;
}

function Poly({ ps, className }: { ps: P3[]; className?: string }) {
  return <polygon className={className} points={pts(ps)} />;
}

/** Faint floor grid on z = 0, like a drafting sheet. */
function Grid({ x0, x1, y0, y1 }: { x0: number; x1: number; y0: number; y1: number }) {
  const out: ReactElement[] = [];
  for (let x = x0; x <= x1; x += 2) out.push(<Line key={`x${x}`} a={[x, y0, 0]} b={[x, y1, 0]} />);
  for (let y = y0; y <= y1; y += 2) out.push(<Line key={`y${y}`} a={[x0, y, 0]} b={[x1, y, 0]} />);
  return <g className={s.grid}>{out}</g>;
}

/** An open tray: rim box with a sunken floor. */
function Tray({ x0, x1, y0, y1, z0, h }: { x0: number; x1: number; y0: number; y1: number; z0: number; h: number }) {
  const z1 = z0 + h; const i = 0.35;
  return (
    <g>
      <Box a={[x0, y0, z0]} b={[x1, y1, z1]} />
      <Poly className={s.well} ps={[[x0 + i, y0 + i, z1], [x1 - i, y0 + i, z1], [x1 - i, y1 - i, z1], [x0 + i, y1 - i, z1]]} />
      <Poly className={s.floor} ps={[[x0 + i, y0 + i, z0 + 0.15], [x1 - i, y0 + i, z0 + 0.15], [x1 - i, y1 - i, z0 + 0.15], [x0 + i, y1 - i, z0 + 0.15]]} />
      <Line className={s.thin} a={[x0 + i, y1 - i, z1]} b={[x0 + i, y1 - i, z0 + 0.15]} />
      <Line className={s.thin} a={[x1 - i, y0 + i, z1]} b={[x1 - i, y0 + i, z0 + 0.15]} />
    </g>
  );
}

/** A cubic curve through projected points (for the cable). */
function curve(a: P3, c1: P3, c2: P3, b: P3) {
  const f = (p: P3) => pr(p).map(n => n.toFixed(1)).join(" ");
  return `M ${f(a)} C ${f(c1)}, ${f(c2)}, ${f(b)}`;
}

function Machine({ kind }: { kind: EmptyKind }) {
  const unplugged = kind === "error";
  const lamps = [1.9, 2.9, 3.9, 4.9];
  return (
    <g>
      <Grid x0={-1} x1={13} y0={-1} y1={11} />
      {/* outlet on the floor; the cable runs from the cabinet's left face */}
      <Box a={[9, 9.6, 0]} b={[10.4, 11, 0.9]} />
      <Line className={s.thin} a={[9.4, 11, 0.45]} b={[9.9, 11, 0.45]} />
      <path className={unplugged ? s.cable : s.cableOn}
        d={unplugged ? curve([2.4, 6, 2.6], [2.4, 9.2, 2.2], [2.6, 10.3, 0], [4.4, 10.3, 0]) : curve([2.4, 6, 2.6], [2.4, 9.5, 2.2], [5, 11.6, 0], [9.6, 11, 0.45])} />
      {/* plinth and cabinet */}
      <Box a={[0, 0, 0]} b={[12, 7, 1]} />
      <Box a={[1, 1, 1]} b={[7, 6, 7.4]} />
      {/* feed slot on top */}
      <Poly className={s.slot} ps={[[2.4, 3.2, 7.4], [5.6, 3.2, 7.4], [5.6, 3.7, 7.4], [2.4, 3.7, 7.4]]} />
      {/* window and lamps on the front-right face */}
      <Poly className={s.window} ps={[[7, 1.7, 3], [7, 5.3, 3], [7, 5.3, 5.4], [7, 1.7, 5.4]]} />
      <Line className={s.thin} a={[7, 1.7, 4.2]} b={[7, 5.3, 4.2]} />
      {lamps.map((y, i) => {
        const [cx, cy] = pr([7, y + 0.4, 6.4]);
        return <ellipse key={y} className={kind === "loading" ? s.lampRun : s.lamp} style={{ animationDelay: `${i * 0.25}s` }}
          cx={cx} cy={cy} rx={1.9} ry={2.4} />;
      })}
      {/* output chute and tray */}
      <Poly className={s.slot} ps={[[7, 2.4, 1.6], [7, 4.8, 1.6], [7, 4.8, 2.2], [7, 2.4, 2.2]]} />
      <Tray x0={7.6} x1={11.2} y0={1.8} y1={5.4} z0={1} h={0.9} />
      {/* a pull lever at the back-right, as in a drafting of a machine */}
      <Line a={[6.2, 1, 6.2]} b={[6.2, -0.6, 8.6]} />
      <circle className={s.knob} cx={pr([6.2, -0.6, 8.6])[0]} cy={pr([6.2, -0.6, 8.6])[1]} r={2.6} />

      {kind === "nothing_selected" && (
        <g>
          {/* a ledger sheet waiting in the feed slot */}
          <Poly className={s.sheet} ps={[[2.7, 3.45, 7.4], [5.3, 3.45, 7.4], [5.3, 3.45, 10.4], [2.7, 3.45, 10.4]]} />
          {[8.2, 8.8, 9.4, 10].map(z => <Line key={z} className={s.rule} a={[3, 3.45, z]} b={[5, 3.45, z]} />)}
        </g>
      )}
      {kind === "unknown_entity" && (
        <g>
          {/* a card it does not recognise, held above the slot */}
          <Poly className={s.ghost} ps={[[2.7, 3.45, 9], [5.3, 3.45, 9], [5.3, 3.45, 11.4], [2.7, 3.45, 11.4]]} />
          <Line className={s.ghostLine} a={[4, 3.45, 8.8]} b={[4, 3.45, 7.6]} />
        </g>
      )}
      {unplugged && (
        <g>
          {/* the plug lies short of the outlet */}
          <Box cls={s.plug} a={[4.4, 9.8, 0]} b={[5.6, 10.8, 0.7]} />
          <Line className={s.prong} a={[5.6, 10.1, 0.35]} b={[6.3, 10.1, 0.35]} />
          <Line className={s.prong} a={[5.6, 10.5, 0.35]} b={[6.3, 10.5, 0.35]} />
        </g>
      )}
    </g>
  );
}

function EmptyTray() {
  return (
    <g>
      <Grid x0={-2} x1={12} y0={-2} y1={10} />
      <Tray x0={0} x1={10} y0={0} y1={8} z0={0} h={1.6} />
      {/* where a sheet would lie */}
      <Poly className={s.ghost} ps={[[2, 2, 0.2], [8, 2, 0.2], [8, 6, 0.2], [2, 6, 0.2]]} />
    </g>
  );
}

/** Bounds of the projected scene, so the viewBox hugs the drawing. */
function viewBox(kind: EmptyKind) {
  const corners: P3[] = kind === "empty"
    ? [[-2, -2, 0], [12, -2, 0], [12, 10, 0], [-2, 10, 0], [0, 0, 1.6]]
    : [[-1, -1, 0], [13, -1, 0], [13, 11, 0], [-1, 11, 0], [6.2, -0.6, 8.6], [1, 1, 7.4],
      ...(kind === "unknown_entity" ? [[2.7, 3.45, 11.4] as P3] : kind === "nothing_selected" ? [[2.7, 3.45, 10.4] as P3] : [])];
  const ps = corners.map(pr);
  const xs = ps.map(p => p[0]); const ys = ps.map(p => p[1]);
  const pad = 4;
  const x = Math.min(...xs) - pad; const y = Math.min(...ys) - pad;
  return `${x.toFixed(0)} ${y.toFixed(0)} ${(Math.max(...xs) - x + pad).toFixed(0)} ${(Math.max(...ys) - y + pad).toFixed(0)}`;
}

export default function EmptyStateArt({ kind }: { kind: EmptyKind }) {
  return (
    <svg className={s.art} viewBox={viewBox(kind)} aria-hidden="true" focusable="false">
      {kind === "empty" ? <EmptyTray /> : <Machine kind={kind} />}
    </svg>
  );
}
