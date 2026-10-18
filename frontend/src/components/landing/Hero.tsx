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
        <p className={s.eyebrow}>Moot · Company Brain on FalkorDB · Graph Hacks, Company Brain track · <a className="link" href="#judges">tour for judges</a></p>
        <h1 id="hero-title" className={`t-hero ${s.title}`}>Ask an organisation whether a decision still holds, and who answers for it.</h1>
        <p className={`t-lead ${s.lead}`}>
          Moot reads decisions, people and teams into a FalkorDB graph with dates on every edge. Kubernetes is in it: every SIG Auth, Node, Network and Storage proposal and every SIG lead since 2018. Each answer shows the path and the Cypher behind it.
        </p>
        <div className={s.actions}>
          <Link href="/app/?graph=gh_kubernetes_enhancements" className="btn">Ask Kubernetes</Link>
          <a href="#how" className={`link ${s.more}`}>See how it works ›</a>
        </div>
        <p className={`t-footnote ${s.jump}`}>
          Straight to the proof: <Link href="/app/ledger/?graph=gh_kubernetes_enhancements&d=KEP-3130" className="link">KEP-3130: retired, by what, who answers for it</Link> ·{" "}
          <Link href="/app/ledger/?graph=gh_kubernetes_enhancements&d=KEP-3130&tab=cypher" className="link">the Cypher FalkorDB ran</Link> ·{" "}
          <Link href="/app/ledger/?graph=larkspur&d=D01&tab=graph" className="link">a demo company, eight people deep</Link> ·{" "}
          <Link href="/app/people/?graph=larkspur" className="link">what leaves when someone does</Link> ·{" "}
          <Link href="/app/ledger/?graph=gh_thomvaill_log4brains" className="link">a real GitHub repo, audited</Link>
        </p>
        <HeroField ledger={ledger.data} timeline={timeline.data} error={ledger.error ?? timeline.error} />
      </div>
    </section>
  );
}
