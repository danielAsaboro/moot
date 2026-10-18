"use client";
// Ordered-dither band for an exhibit card: ink squares on paper. The band runs from the decision date (left) to the
// audit's as-of date (right); the ink is densest where the evidence landed. The grain is seeded by the evidence id.
import { useMemo } from "react";

const W = 72, H = 12;
const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5].map(v => (v + 0.5) / 16);

function rng(seed: string) {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) h = Math.imul(h ^ seed.charCodeAt(i), 16777619);
  return () => {
    h = (h + 0x6d2b79f5) | 0;
    let t = Math.imul(h ^ (h >>> 15), 1 | h);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Where `at` falls between `from` and `to`, 0..1. */
export function datePosition(at: string, from?: string | null, to?: string | null): number {
  const a = Date.parse(at), f = from ? Date.parse(from) : NaN, t = to ? Date.parse(to) : NaN;
  if ([a, f, t].some(Number.isNaN) || t <= f) return 0.5;
  return Math.min(1, Math.max(0, (a - f) / (t - f)));
}

export default function EvidenceDither({ seed, position, className }: { seed: string; position: number; className?: string }) {
  const d = useMemo(() => {
    const r = rng(seed);
    let out = "";
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const dx = x / (W - 1) - position;
        const peak = Math.exp(-(dx * dx) / (2 * 0.11 * 0.11));
        const v = 0.04 + 0.86 * peak * (0.75 + 0.25 * (y / (H - 1))) + (r() - 0.5) * 0.22;
        if (v > BAYER[(y % 4) * 4 + (x % 4)]) out += `M${x} ${y}h1v1h-1z`;
      }
    }
    return out;
  }, [seed, position]);
  return (
    <svg className={className} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">
      <path d={d} fill="currentColor" shapeRendering="crispEdges" />
      <rect x={Math.round(position * (W - 1))} y={0} width={0.35} height={H} fill="currentColor" />
    </svg>
  );
}
