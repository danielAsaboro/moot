"use client";
// The reason as a module with a cable to every decision that rests on it, drawn unplugged (the what-if exhibit).
// One tap per decision row the API returned; a small junction on a cable for each reason the path passes through.
// The list under the figure carries the links and the verdicts; the figure shows the shape.
import type { WhatIfDecision } from "@/lib/types";
import { longDate } from "@/lib/format";
import { cx } from "@/components/ui";
import s from "./whatif.module.css";

// Isometric projection of a box (x along the right-down axis, y along the left-down axis, z up).
const C = Math.cos(Math.PI / 6), S = 0.5;
const iso = (x: number, y: number, z: number, ox: number, oy: number) => `${ox + (x - y) * C},${oy + (x + y) * S - z}`;

function ModuleDrawing() {
  const a = 64, b = 64, h = 24, ox = 64, oy = 14 + h;
  const P = (x: number, y: number, z: number) => iso(x, y, z, ox, oy);
  // the socket sits low on the front-left face, right above the trunk (x = 20), where the cable used to plug in
  const sock = [P(a * 0.08, b, h * 0.25), P(a * 0.33, b, h * 0.25), P(a * 0.33, b, h * 0.7), P(a * 0.08, b, h * 0.7)].join(" ");
  return (
    <svg className={s.moduleSvg} viewBox="0 0 128 112" aria-hidden="true">
      <polygon className={s.isoTop} points={[P(0, 0, h), P(a, 0, h), P(a, b, h), P(0, b, h)].join(" ")} />
      <polygon className={s.isoLeft} points={[P(0, b, h), P(a, b, h), P(a, b, 0), P(0, b, 0)].join(" ")} />
      <polygon className={s.isoRight} points={[P(a, 0, h), P(a, b, h), P(a, b, 0), P(a, 0, 0)].join(" ")} />
      <polygon className={s.isoInset} points={[P(a * 0.22, b * 0.22, h), P(a * 0.78, b * 0.22, h), P(a * 0.78, b * 0.78, h), P(a * 0.22, b * 0.78, h)].join(" ")} />
      <polygon className={s.isoSocket} points={sock} />
    </svg>
  );
}

export default function WhatIfWiring({ premise, decisions, asOf, depth }: {
  premise: { id: string; text: string; kind?: string }; decisions: WhatIfDecision[]; asOf: string; depth: number;
}) {
  const kind = premise.kind ? premise.kind.charAt(0).toUpperCase() + premise.kind.slice(1) : "Reason";
  return (
    <figure className={s.wiring}>
      <div className={s.module}>
        <ModuleDrawing />
        <div className={s.moduleText}>
          <span className="t-footnote">{kind} · <span className="id">{premise.id}</span></span>
          <p className={s.moduleTitle}>{premise.text}</p>
        </div>
      </div>

      {/* the pulled plug: a gap under the socket, then the dead cable */}
      <div className={s.plugRow} aria-hidden="true">
        <svg className={s.plug} viewBox="0 0 40 40" preserveAspectRatio="xMinYMin meet">
          <path className={s.plugPins} d="M17.5 16 V11 M22.5 16 V11" />
          <rect className={s.plugBody} x={15} y={16} width={10} height={9} rx={2} />
          <path className={s.dead} d="M20 25 V40" />
        </svg>
        <span className={s.plugText}>Unplugged</span>
      </div>

      <ul className={s.bus}>
        {decisions.map((d, i) => {
          const junctions = Math.max(0, d.hops - 1);
          const lastRow = i === decisions.length - 1;
          const tone = d.flips ? s.dead : d.before === "MOOT" ? s.wasDead : s.live;
          return (
            <li key={d.id} className={s.tap}>
              <span className={s.cableCell} aria-hidden="true"><svg className={s.cable}>
                <line className={s.dead} x1={20} y1={0} x2={20} y2={lastRow ? "50%" : "100%"} />
                <line className={tone} x1={20} y1="50%" x2="100%" y2="50%" />
                {Array.from({ length: junctions }, (_, k) => (
                  <rect key={k} className={cx(s.junction, tone)} x={20 + (k + 1) * (24 / (junctions + 1)) - 4} y="50%" width={8} height={8} rx={2} transform="translate(0 -4)" />
                ))}
              </svg></span>
              <span className={cx(s.dmod, d.flips && s.flips)}>
                <span className={s.dmodTitle}><span className="id">{d.id}</span> {d.title}</span>
                <span className={s.dmodNote}>
                  {d.flips ? "Would fall" : d.before === "MOOT" ? "Already moot" : "Stays standing"}
                  {junctions > 0 && <> · via {d.path.slice(1, -1).map((n, k) => <span key={n.id}>{k ? ", " : ""}<span className="id">{n.id}</span></span>)}</>}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
      <figcaption className={cx("t-caption", s.figcap)}>
        <span className="id">{premise.id}</span> unplugged as of {longDate(asOf)}, followed up to {depth} {depth === 1 ? "hop" : "hops"}.
      </figcaption>
    </figure>
  );
}
