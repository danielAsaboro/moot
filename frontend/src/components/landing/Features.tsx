"use client";
// Features: six quiet tiles. Hovering or focusing one lifts a card out of it with a real Larkspur example. The examples
// load when the section scrolls near the viewport, or on the first hover or focus, whichever comes first.
import { useCallback, useEffect, useRef, useState, type ComponentType } from "react";
import Link from "next/link";
import { SectionHead } from "@/components/ui";
import { longDate } from "@/lib/format";
import { REF_DATE } from "./FeatureData";
import { DepthCard, GateCard, HandoverCard, PathCard, TimeCard, WhatIfCard } from "./FeatureCards";
import s from "./Features.module.css";

interface Tile { title: string; text: string; href: string; cta: string; Card: ComponentType<{ armed: boolean }> }

const TILES: Tile[] = [
  { title: "Path verdicts", text: "Every verdict comes with the path that decided it: decision, reason, evidence.",
    href: `/app/?d=D01&as_of=${REF_DATE}`, cta: "Open D01", Card: PathCard },
  { title: "Time travel", text: "Read a decision as of any date. Evidence counts only from the day it was on record.",
    href: `/app/?d=D07&as_of=${REF_DATE}`, cta: "Open D07", Card: TimeCard },
  { title: "Depth", text: "Reasons rest on other reasons. Choose how many hops Moot walks before it rules.",
    href: `/app/?d=D01&as_of=${REF_DATE}&depth=1`, cta: "Open D01 at depth 1", Card: DepthCard },
  { title: "Agent gate", text: "Before an agent acts on a rule, it asks. The gate answers ALLOW, DENY or REVALIDATE.",
    href: "/app/gate/?graph=larkspur", cta: "Open the gate board", Card: GateCard },
  { title: "What-if", text: "Take one reason away and see which decisions would fall with it.",
    href: "/app/whatif/?graph=larkspur", cta: "Open what-if", Card: WhatIfCard },
  { title: "Handover", text: "When someone leaves, their decisions are routed up the reporting line, not lost.",
    href: "/app/orphans/?graph=larkspur", cta: "Open handover", Card: HandoverCard },
];

export default function Features() {
  const ref = useRef<HTMLElement>(null);
  const [armed, setArmed] = useState(false);
  const arm = useCallback(() => setArmed(true), []);

  useEffect(() => {
    const el = ref.current;
    if (!el || armed) return;
    if (typeof IntersectionObserver === "undefined") { setArmed(true); return; }
    const io = new IntersectionObserver(es => { if (es.some(e => e.isIntersecting)) setArmed(true); }, { rootMargin: "240px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [armed]);

  return (
    <section id="features" ref={ref} className={s.section} aria-label="Features">
      <div className="wrap">
        <SectionHead eyebrow="03 · Features" title="Six ways to read the same graph">
          Each tile holds a real example from Larkspur, read as of {longDate(REF_DATE)}. Hover or focus a tile to see it.
        </SectionHead>
        <ul className={s.grid}>
          {TILES.map((t, i) => (
            <li key={t.title} className={s.cell}>
              <Link href={t.href} className={s.tile} onPointerEnter={arm} onFocus={arm}>
                <span className={s.num}>{String(i + 1).padStart(2, "0")}</span>
                <h3 className={s.tileTitle}>{t.title}</h3>
                <p className={s.text}>{t.text}</p>
                <span className={s.cta}>{t.cta} <span aria-hidden="true">→</span></span>
                <div className={s.slot}>
                  <span className={s.hint} aria-hidden="true">Example</span>
                  <div className={s.card}><t.Card armed={armed} /></div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
