"use client";
// The ruled-ledger field, framed as the hero's one visual, with a quiet control row and a one-line caption.
// Steps month by month through the timeline points the API returned; tokens in a point's `moot` list sink.
// Autoplay runs once on arrival and stops at the latest point; it pauses on hover and while the scrubber has
// focus. Reduced motion starts (and stays) on the final state.
import dynamic from "next/dynamic";
import { Component, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { LedgerResponse, TimelinePoint, TimelineResponse } from "@/lib/types";
import EmptyState from "@/components/ui/EmptyState";
import s from "./Hero.module.css";
import HeroFieldFlat from "./HeroFieldFlat";
import { useMedia, useReducedMotion, useVisible } from "./HeroHooks";
import { layoutTokens, tokenStates, type FieldToken } from "./HeroModel";

const Field3D = dynamic(() => import("./HeroField3D"), { ssr: false, loading: () => null });
const STEP_MS = 800;

class CanvasBoundary extends Component<{ onError: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { this.props.onError(); }
  render() { return this.state.failed ? null : this.props.children; }
}

function hasWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch { return false; }
}

const monthYear = (iso: string) => {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
};
const mootAt = (p: TimelinePoint | undefined) => (p ? (p.counts.MOOT ?? p.moot.length) : 0);
const presentAt = (tokens: FieldToken[], p: TimelinePoint | undefined) => (p ? tokens.filter(t => t.decided_on <= p.as_of).length : tokens.length);

export default function HeroField({ ledger, timeline, error }: { ledger: LedgerResponse | null; timeline: TimelineResponse | null; error: string | null }) {
  const narrow = useMedia("(max-width: 640px)");
  const reduced = useReducedMotion();
  const box = useRef<HTMLDivElement>(null);
  const visible = useVisible(box);

  const points = useMemo(() => timeline?.points ?? [], [timeline]);
  const last = Math.max(0, points.length - 1);
  const cols = narrow ? 6 : 10;
  const tokens = useMemo(() => layoutTokens(ledger?.decisions ?? [], cols), [ledger, cols]);
  const rows = Math.max(1, Math.ceil(tokens.length / cols));

  const [idx, setIdx] = useState<number | null>(null);   // null = final state (before autoplay starts)
  const [playing, setPlaying] = useState(false);
  const [started, setStarted] = useState(false);
  const [hover, setHover] = useState(false);
  const [scrubFocus, setScrubFocus] = useState(false);
  const [gl, setGl] = useState<"unknown" | "ok" | "none">("unknown");
  const [ready, setReady] = useState(false);

  useEffect(() => { setGl(hasWebGL() ? "ok" : "none"); }, []);

  // Start once, the first time the field is on screen with data and motion allowed.
  useEffect(() => {
    if (started || !points.length || !visible || reduced) return;
    setStarted(true); setIdx(0); setPlaying(true);
  }, [started, points.length, visible, reduced]);

  const at = idx ?? last;
  const paused = hover || scrubFocus || !visible;
  useEffect(() => {
    if (!playing || paused) return;
    if (at >= last) { setPlaying(false); return; }
    const t = setTimeout(() => setIdx(at + 1), at === 0 ? STEP_MS * 1.6 : STEP_MS);
    return () => clearTimeout(t);
  }, [playing, paused, at, last]);

  const point = points[at];
  const states = useMemo(() => tokenStates(tokens, point), [tokens, point]);
  const moot = mootAt(point);
  const present = presentAt(tokens, point);
  const final = points[last];

  const toggle = () => {
    if (playing) { setPlaying(false); return; }
    if (at >= last) setIdx(0);
    setStarted(true); setPlaying(true);
  };

  if (error) {
    return (
      <figure className={s.figure}>
        <div className={`${s.stage} ${s.stageMsg}`}><EmptyState kind="error" title="The ledger could not be loaded." detail={error} /></div>
      </figure>
    );
  }

  const loaded = !!ledger && points.length > 0;
  return (
    <figure className={s.figure} aria-labelledby="hero-field-caption">
      <div ref={box} className={s.stage} onPointerEnter={() => setHover(true)} onPointerLeave={() => setHover(false)}>
        {!loaded && <div className={s.stageLoading}><span className="skeleton" style={{ width: "40%" }} /><span className="skeleton" style={{ width: "62%" }} /></div>}
        {loaded && (
          <>
            <div className={`${s.flatWrap} ${ready ? s.flatGone : ""}`}>
              <HeroFieldFlat tokens={tokens} states={states} cols={cols} rows={rows} />
            </div>
            {gl === "ok" && (
              <div className={s.canvasWrap}>
                <CanvasBoundary onError={() => { setGl("none"); setReady(false); }}>
                  <Field3D
                    tokens={tokens} states={states} cols={cols} rows={rows} asOf={point?.as_of ?? ""}
                    reduced={reduced} active={visible} showAllLabels={!narrow} onReady={() => setReady(true)}
                  />
                </CanvasBoundary>
              </div>
            )}
          </>
        )}
        {point && (
          <p className="sr-only" aria-live={playing && !paused ? "off" : "polite"}>
            As of {point.as_of}, {moot} of {present} decisions on the ledger are moot{point.moot.length ? `: ${point.moot.join(", ")}` : ""}.
          </p>
        )}
      </div>

      <div className={s.bar}>
        <button type="button" className={s.play} onClick={toggle} disabled={!loaded} aria-label={playing ? "Pause the timeline" : "Play the timeline"}>
          {playing ? "Pause" : at >= last && started ? "Replay" : "Play"}
        </button>
        <label className={s.scrub}>
          <span className="sr-only">Timeline date</span>
          <input
            type="range" min={0} max={last} step={1} value={at} disabled={!loaded}
            aria-valuetext={point ? `as of ${point.as_of}, ${moot} moot` : undefined}
            onChange={e => { setPlaying(false); setStarted(true); setIdx(Number(e.target.value)); }}
            onFocus={() => setScrubFocus(true)} onBlur={() => setScrubFocus(false)}
          />
        </label>
        <p className={`t-footnote tabular ${s.readout}`} aria-hidden="true">
          {point ? <>as of {point.as_of} · <span className={moot ? s.mootCount : undefined}>{moot} moot</span></> : <span className={`skeleton ${s.readSkel}`} />}
        </p>
      </div>

      <figcaption id="hero-field-caption" className={`t-sub ${s.caption}`}>
        <span className="lead-in">Larkspur, month by month.</span> Each token is a standing decision.
        When a reason dies, it sinks below the line.
        {final && loaded && <> By {monthYear(final.as_of)}, {mootAt(final)} of {presentAt(tokens, final)} had.</>}
      </figcaption>
    </figure>
  );
}
