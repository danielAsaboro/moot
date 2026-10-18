"use client";
// Site footer: one closing line and action, the Moot wordmark extruded in stacked line layers (the page's finale),
// then one quiet row of links and the disclosure. The extrusion is stacked text, not WebGL: it uses the real display
// face, needs no canvas and is a flat wordmark before scripts run. It rises once on view and leans with the pointer;
// with reduced motion it stands still, already raised.
import Link from "next/link";
import { useEffect, useRef } from "react";
import { API_BASE } from "@/lib/api";
import s from "./SiteFooter.module.css";

const LAYERS = 26;
const SOURCE = "https://github.com/danielAsaboro/moot";

function Mark() {
  return <>M<s>oo</s>t</>;
}

export default function SiteFooter() {
  const stage = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = stage.current;
    if (!el) return;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)");
    // Raise the extrusion once the wordmark scrolls into view; reduced motion shows it raised at once.
    if (reduce.matches || !("IntersectionObserver" in window)) { el.dataset.raised = "1"; return; }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { el.dataset.raised = "1"; io.disconnect(); } }, { threshold: 0.2 });
    io.observe(el);
    let raf = 0;
    const move = (ev: PointerEvent) => {
      if (reduce.matches) return;
      const r = el.getBoundingClientRect();
      const px = Math.max(-1, Math.min(1, ((ev.clientX - r.left) / r.width) * 2 - 1));
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => el.style.setProperty("--px", px.toFixed(3)));
    };
    const foot = el.closest("footer") ?? el;
    foot.addEventListener("pointermove", move as EventListener);
    return () => { io.disconnect(); cancelAnimationFrame(raf); foot.removeEventListener("pointermove", move as EventListener); };
  }, []);

  return (
    <footer className={s.footer}>
      <div className={`wrap ${s.close}`}>
        <h2 className="t-display">Ask why your team does something.</h2>
        <Link href="/app/" className="btn">Ask Moot</Link>
      </div>

      <div ref={stage} className={s.stage} aria-hidden="true">
        <div className={s.word} style={{ ["--n" as string]: LAYERS + 1 }}>
          {Array.from({ length: LAYERS }, (_, k) => {
            const i = LAYERS - k; // deepest first, so the face paints last
            return <span key={i} className={s.layer} style={{ ["--i" as string]: i }}><Mark /></span>;
          })}
          <span className={`${s.layer} ${s.face}`}><Mark /></span>
        </div>
      </div>

      <div className={`wrap ${s.base}`}>
        <nav aria-label="Footer" className={s.links}>
          <Link href="/app/">Ask</Link>
          <Link href="/app/ledger/">Ledger</Link>
          <Link href="/app/gate/">Agent gate</Link>
          <Link href="/app/realworld/">Real world</Link>
          <a href={SOURCE} target="_blank" rel="noopener">Source on GitHub<span aria-hidden="true"> ↗</span></a>
          <a href={`${API_BASE}/docs`}>API docs</a>
        </nav>
        <p className="t-footnote">Built for Graph Hacks · FalkorDB. Larkspur is fictional; the public records are real.</p>
      </div>
    </footer>
  );
}
