"use client";
// A very faint ordered (Bayer 4x4) dither, used only as a printed texture behind the keynote number in Proof.
import { useId } from "react";
import s from "./Proof.module.css";

const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];
const CELL = 3;

/** A full-bleed dither field with `level` of 16 cells inked; decorative, hidden from assistive tech. */
export function DitherField({ level = 2 }: { level?: number }) {
  const id = `d${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  return (
    <svg className={s.dither} aria-hidden="true" focusable="false" width="100%" height="100%">
      <defs>
        <pattern id={id} width={CELL * 4} height={CELL * 4} patternUnits="userSpaceOnUse">
          <g fill="currentColor">
            {BAYER.map((t, i) => (t < level ? <rect key={i} x={(i % 4) * CELL} y={Math.floor(i / 4) * CELL} width={CELL - 1} height={CELL - 1} /> : null))}
          </g>
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#${id})`} />
    </svg>
  );
}
