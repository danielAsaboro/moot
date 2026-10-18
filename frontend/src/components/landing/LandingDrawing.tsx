"use client";
// Landing section 5, the one dark band: the real isometric drawing of D01, fetched and mounted only when the band
// nears the viewport. The band is dark in both themes; the drawing reads the night tokens set on its frame
// (IsoGraph reads its colours from its own element, so the 3D scene follows them too).
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import IsoGraph from "@/components/graph/IsoGraph";
import s from "./LandingDrawing.module.css";

const ID = "D01";
const AS_OF = "2026-10-16";
const DEPTH = 4;

/** True once the element comes within `margin` of the viewport; stays true. */
function useNear<T extends Element>(margin = "600px") {
  const ref = useRef<T>(null);
  const [near, setNear] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || near) return;
    if (typeof IntersectionObserver === "undefined") { setNear(true); return; }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setNear(true); io.disconnect(); } }, { rootMargin: margin });
    io.observe(el);
    return () => io.disconnect();
  }, [margin, near]);
  return [ref, near] as const;
}

function Drawing() {
  const { data, error, loading } = useApi(() => api.decision(ID, { as_of: AS_OF, depth: DEPTH }), []);
  if (loading) return <div className={s.placeholder} aria-busy="true"><span className="t-footnote">Drawing {ID}…</span></div>;
  if (error || !data) {
    return (
      <div className={s.placeholder} role="status">
        <p className="t-callout">The drawing could not be loaded.</p>
        {error && <p className="t-footnote">{error}</p>}
      </div>
    );
  }
  return (
    <div className={s.frame} data-ground="night">
      <IsoGraph audit={data.audit} gate={data.gate} height={520} />
    </div>
  );
}

export default function LandingDrawing() {
  const [ref, near] = useNear<HTMLDivElement>();
  return (
    <section id="drawing" className={s.band} aria-labelledby="drawing-title">
      <div className={`wrap ${s.inner}`} ref={ref}>
        <div className="t-eyebrow">The drawing</div>
        <h2 id="drawing-title" className={`t-display ${s.title}`}>Every verdict comes with its drawing.</h2>
        <p className={`t-lead ${s.lead}`}>
          The decision, its reasons and the evidence, drawn from the rows FalkorDB returned. The cable to the expired reason
          is unplugged. Drag to turn it.
        </p>
        <div className={s.stage}>
          {near ? <Drawing /> : <div className={s.placeholder} aria-hidden="true" />}
        </div>
        <Link href={`/app/?graph=larkspur&d=${ID}&as_of=${AS_OF}&depth=${DEPTH}`} className={s.open}>
          Open <span className="id">{ID}</span> in the ledger <span aria-hidden="true">›</span>
        </Link>
      </div>
    </section>
  );
}
