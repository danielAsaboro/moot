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
          <Link href="/app/" className="btn">Ask Moot</Link>
          <a href="#how" className={`link ${s.more}`}>See how it works ›</a>
        </div>
        <p className={`t-footnote ${s.jump}`}>
          Straight to the proof: <Link href="/app/ledger/?d=D01&tab=graph" className="link">the evidence path for the 10 MB cap</Link> ·{" "}
          <Link href="/app/ledger/?d=D01&tab=cypher" className="link">the Cypher FalkorDB ran</Link> ·{" "}
          <Link href="/app/people/" className="link">what leaves when someone does</Link> ·{" "}
          <Link href="/app/ledger/?graph=gh_alphagov_govuk_infrastructure" className="link">a real GitHub repo, audited</Link>
        </p>
        <HeroField ledger={ledger.data} timeline={timeline.data} error={ledger.error ?? timeline.error} />
      </div>
    </section>
  );
}
