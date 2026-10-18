"use client";
// The ruled-ledger field drawn flat in SVG: shown until the 3D canvas mounts, and instead of it when WebGL
// is unavailable. Same tokens and states as the 3D field; MOOT tokens sit below their line in accent.
import s from "./Hero.module.css";
import type { FieldToken, TokenState } from "./HeroModel";

const PX = 92, PY = 74, TW = 60, TH = 22, PAD = 26;

export default function HeroFieldFlat({ tokens, states, cols, rows }: { tokens: FieldToken[]; states: TokenState[]; cols: number; rows: number }) {
  const w = PAD * 2 + (cols - 1) * PX + TW, h = PAD * 2 + rows * PY;
  const fine = Array.from({ length: Math.ceil(h / 9) }, (_, i) => i * 9 + 4);
  return (
    <svg className={s.flat} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      {fine.map(y => <line key={y} x1={-400} x2={w + 400} y1={y} y2={y} className={s.flatFine} />)}
      {tokens.map((t, i) => {
        const st = states[i] ?? "float";
        const line = PAD + t.row * PY + PY * 0.62;
        const x = PAD + t.col * PX;
        const y = st === "moot" ? line - TH * 0.3 : line - TH - 8;
        return (
          <g key={t.id} className={st === "moot" ? s.flatMoot : st === "ghost" ? s.flatGhost : s.flatFloat}>
            <rect x={x} y={y} width={TW} height={TH} rx={2} />
            <text x={x + TW / 2} y={y - 6} textAnchor="middle">{t.id}</text>
          </g>
        );
      })}
      {Array.from({ length: rows }, (_, r) => {
        const y = PAD + r * PY + PY * 0.62;
        return <line key={`r${r}`} x1={-400} x2={w + 400} y1={y} y2={y} className={s.flatRow} />;
      })}
    </svg>
  );
}
