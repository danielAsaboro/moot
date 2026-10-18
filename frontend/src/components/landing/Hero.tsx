"use client";
// Landing hero: eyebrow, headline, one lead sentence, two actions, then the ruled-ledger field as the one visual.
// The field shows Larkspur's real ledger and timeline: decisions sink below the line as their reasons die.
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import s from "./Hero.module.css";
import HeroField from "./HeroField";

const DEPTH = 4;
const AS_OF = "2026-10-16";   // the spec's reference date

export default function Hero() {
  const ledger = useApi(() => api.ledger({ as_of: AS_OF, depth: DEPTH }), []);
  const timeline = useApi(() => api.timeline(DEPTH), []);

  return (
    <section id="top" className={s.hero} aria-labelledby="hero-title">
      <div className={`wrap ${s.inner}`}>
        <p className={s.eyebrow}>Moot</p>
        <h1 id="hero-title" className={`t-hero ${s.title}`}>Find the rules your team follows for reasons that no longer exist.</h1>
        <p className={`t-lead ${s.lead}`}>
          Moot checks the reason behind every standing decision against dated evidence, and shows you the path it took.
        </p>
        <div className={s.actions}>
          <Link href="/app/" className="btn">Open the ledger</Link>
          <a href="#how" className={`link ${s.more}`}>See how it works ›</a>
        </div>
        <HeroField ledger={ledger.data} timeline={timeline.data} error={ledger.error ?? timeline.error} />
      </div>
    </section>
  );
}
