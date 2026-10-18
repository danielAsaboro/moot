"use client";
// The isometric drawing of one audit. The decision is the central module, premises sit on rings by hop and plug into
// it with cables along their path, evidence slabs sit on the outer ring. An expired premise's cable is unplugged.
// Every part is a row the API returned; the 2D path chains are the fallback.
//
// variant="full"    the Graph tab and the landing page's dark band: orbit ±25°, callouts, parts list, controls.
// variant="preview" the hero of the decision page: same scene, framed, static, three callouts; a button if onExpand.
// ground="night"    draws on the dark --night ground in either theme (also when an ancestor has data-ground="night").
import { Component, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import dynamic from "next/dynamic";
import type { Audit, Gate } from "@/lib/types";
import { GateBadge, Group, PathChain, Row, Segmented, StateTag, cx, decidingEvent } from "@/components/ui";
import { longDate } from "@/lib/format";
import { layoutAudit, visibleParts, type Drawing, type Part } from "./layout";
import { createProjStore, type ViewApi } from "./store";
import { useTokens } from "./useTokens";
import Callouts, { partText, type Mode } from "./Callouts";
import s from "./IsoGraph.module.css";

const IsoScene = dynamic(() => import("./IsoScene"), { ssr: false, loading: () => null });

class SceneBoundary extends Component<{ onError: () => void; children: ReactNode }, { failed: boolean }> {
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

function useMedia(q: string): boolean {
  const [m, setM] = useState(false);
  useEffect(() => {
    const mq = matchMedia(q);
    setM(mq.matches);
    const on = () => setM(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [q]);
  return m;
}

function useWidth(ref: React.RefObject<HTMLElement | null>): number {
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return w;
}

/** The premise that decides the verdict (expired, else disputed, else a supported one) and its deciding evidence. */
function decidingParts(d: Drawing): { premise: Part | null; evidence: Part | null } {
  const ps = d.parts.filter(p => p.kind === "premise");
  const premise = ps.find(p => p.state === "expired") ?? ps.find(p => p.state === "disputed")
    ?? ps.find(p => p.state === "holds" && p.premise?.evidence.length) ?? ps[0] ?? null;
  const evidence = premise ? d.parts.find(p => p.kind === "evidence" && p.parent === premise.key && p.deciding) ?? null : null;
  return { premise, evidence };
}

/** The text version of the drawing: one path chain per premise, ending at the evidence that decides it. */
function Chains({ audit }: { audit: Audit }) {
  const ps = [...audit.premises].sort((a, b) => a.hops - b.hops);
  if (!ps.length) return null;
  return (
    <ol className={s.chains}>
      {ps.map(p => (
        <li key={p.id}>
          <span className={s.chainHead}><span className="id">{p.id}</span> · {p.hops === 1 ? "1 hop" : `${p.hops} hops`} <StateTag state={p.state} /></span>
          <PathChain path={p.path} evidence={decidingEvent(p.evidence)} />
        </li>
      ))}
    </ol>
  );
}

type SwatchKind = "holds" | "expired" | "disputed" | "muted" | "supports" | "unplugged";
function Swatch({ kind }: { kind: SwatchKind }) {
  if (kind === "unplugged") {
    return (
      <svg className={cx(s.sw, s.swAccent)} width="36" height="14" viewBox="0 0 40 14" aria-hidden="true">
        <path d="M1 11 H13 L19 4" /><rect x="18" y="1" width="5" height="4" transform="rotate(-40 20 3)" />
        <rect x="30" y="8" width="6" height="5" strokeDasharray="2 1.5" />
      </svg>
    );
  }
  const cls = { holds: s.swInk, expired: s.swAccent, disputed: s.swDisputed, muted: s.swMuted, supports: s.swHolds }[kind];
  return (
    <svg className={cx(s.sw, cls)} width="36" height="14" viewBox="0 0 40 14" aria-hidden="true">
      <path d="M1 7 H39" strokeDasharray={kind === "muted" ? "3 2.5" : undefined} />
    </svg>
  );
}

const LEGEND: [SwatchKind, string][] = [
  ["holds", "Plugged in: the reason holds"],
  ["unplugged", "Unplugged: the reason expired"],
  ["expired", "Contradicting evidence"],
  ["supports", "Supporting evidence"],
  ["disputed", "Disputed: evidence on both sides"],
  ["muted", "Unchecked, or no dated evidence"],
];

function Detail({ part, audit }: { part: Part; audit: Audit }) {
  if (part.kind === "decision") {
    return (
      <div className={s.detail}>
        <p className={s.dtext}><span className="lead-in">{audit.decision.title}.</span></p>
        <p className="t-footnote">Decided {longDate(audit.decision.decided_on)}. Read as of {longDate(audit.as_of)}, {audit.depth} {audit.depth === 1 ? "hop" : "hops"} deep.</p>
      </div>
    );
  }
  if (part.kind === "premise" && part.premise) {
    const p = part.premise;
    return (
      <div className={s.detail}>
        <p className={s.dtext}>{p.text}</p>
        {p.unchecked && <p className="t-footnote">The check could not be answered: {p.unchecked}</p>}
        {p.contradicted_before_decision && <p className="t-footnote">Contradicted before the decision was made.</p>}
        {!p.evidence.length && <p className="t-footnote">No dated evidence either way.</p>}
        <PathChain path={p.path} evidence={decidingEvent(p.evidence)} />
      </div>
    );
  }
  const e = part.evidence!;
  return (
    <div className={s.detail}>
      <p className={s.dtext}>{e.title}</p>
      {e.quote && <blockquote className={s.quote}>{e.quote}{e.author && <footer>{e.author}, {longDate(e.date)}</footer>}</blockquote>}
      {part.premise && <PathChain path={part.premise.path} evidence={e} />}
    </div>
  );
}

/** Leading marker of a parts-list row: the callout number, or a small module for the decision. */
function Marker({ part }: { part: Part }) {
  if (part.num) return <span className={s.num} aria-hidden="true">{part.num}</span>;
  return (
    <svg className={s.module} width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
      <path d="M11 3 L20 8 L11 13 L2 8 Z" /><path d="M2 8 V13 L11 18 L20 13 V8" /><path d="M11 13 V18" />
    </svg>
  );
}

export default function IsoGraph({ audit, gate, height, variant = "full", onExpand, ground = "auto" }:
  { audit: Audit; gate?: Gate | null; height?: number; variant?: "full" | "preview"; onExpand?: () => void; ground?: "auto" | "night" }) {
  const preview = variant === "preview";
  const h = height ?? (preview ? 300 : 460);
  const night = ground === "night";
  const rootRef = useRef<HTMLElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const stageW = useWidth(stageRef);
  const compact = !preview && stageW > 0 && stageW < 560;
  const [decidingOnly, setDecidingOnly] = useState(false);
  // The preview is wide and short at every size, so its chain always runs to the right.
  const drawing = useMemo(() => layoutAudit(audit, compact ? "down" : "right"), [audit, compact]);
  const parts = useMemo(() => visibleParts(drawing, decidingOnly), [drawing, decidingOnly]);
  const [hovered, setHovered] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const activeKey = preview ? null : hovered ?? pinned;
  const activePart = parts.find(p => p.key === activeKey) ?? null;
  const active = useMemo(() => (activePart ? new Set(activePart.trail) : null), [activePart]);

  const tokens = useTokens(rootRef, night ? "night" : "auto");
  const reduced = useMedia("(prefers-reduced-motion: reduce)");
  const fine = useMedia("(pointer: fine)");
  const [gl, setGl] = useState<"unknown" | "ok" | "none">("unknown");
  const [ready, setReady] = useState(false);
  useEffect(() => { setGl(hasWebGL() ? "ok" : "none"); }, []);
  const onReady = useCallback(() => setReady(true), []);
  const onFail = useCallback(() => { setGl("none"); setReady(false); }, []);

  const store = useMemo(() => createProjStore(), []);
  const viewRef = useRef<ViewApi | null>(null);
  const pad = useMemo(() => (preview ? (stageW < 520 ? { x: 16, top: 30, bottom: 18 } : { x: 28, top: 44, bottom: 26 })
    : compact ? { x: 18, top: 30, bottom: 60 } : { x: 56, top: 72, bottom: 40 }), [preview, compact, stageW]);

  // Clear a pinned part that the evidence filter hid.
  useEffect(() => { if (pinned && !parts.some(p => p.key === pinned)) setPinned(null); }, [parts, pinned]);

  const deciding = useMemo(() => decidingParts(drawing), [drawing]);
  const mode = useMemo<Mode | undefined>(() => (preview ? {
    only: new Set([audit.decision.id, deciding.premise?.key, deciding.evidence?.key].filter((k): k is string => !!k)),
    plain: true, oneLine: stageW < 520,
  } : undefined), [preview, audit.decision.id, deciding, stageW]);

  const hasEvidence = drawing.parts.some(p => p.kind === "evidence");
  const present = new Set<SwatchKind>(["holds"]);
  for (const p of drawing.parts) {
    if (p.state === "expired") present.add("unplugged");
    if (p.state === "disputed") present.add("disputed");
    if (p.state === "unchecked" || p.state === "unevidenced") present.add("muted");
    if (p.rel === "CONTRADICTS") present.add("expired");
    if (p.rel === "SUPPORTS") present.add("supports");
  }

  const retired = audit.verdict === "RETIRED";
  const sup = audit.superseded_by;
  const notes: string[] = [];
  if (retired) notes.push(sup ? `Retired on ${longDate(sup.at)} by ${sup.id}.` : "Retired.");
  if (audit.verdict === "NOT_YET") notes.push(`Not decided yet as of ${longDate(audit.as_of)}.`);
  if (!audit.premises.length) notes.push("No reason recorded, so there is no path to draw.");
  const live = gl === "ok" && tokens;
  const pick = (k: string) => setPinned(p => (p === k ? null : k));
  const label = `Drawing of ${audit.decision.id}, ${audit.decision.title}, as of ${longDate(audit.as_of)}`;

  const scene = live && (
    <div className={cx(s.canvas, !ready && s.hidden)}>
      <SceneBoundary onError={onFail}>
        <IsoScene drawing={drawing} parts={parts} verdict={audit.verdict} tokens={tokens} active={active}
          onHover={setHovered} onPick={pick} store={store} viewRef={viewRef} orbit={!preview && fine} reduced={reduced}
          pad={pad} onReady={onReady} interactive={!preview} settle={preview} />
      </SceneBoundary>
    </div>
  );

  if (preview) {
    const dp = deciding.premise?.premise;
    return (
      <figure ref={rootRef} className={cx(s.fig, s.previewFig, night && s.night)} aria-label={label}>
        <div ref={stageRef} className={cx(s.stage, s.previewStage, retired && s.retired)} style={{ height: h }}>
          {scene}
          {ready && <Callouts store={store} parts={parts} drawing={drawing} audit={audit} compact={false} active={null}
            onHover={() => {}} mode={mode} />}
          {!ready && (
            <div className={s.previewFallback}>
              {gl !== "none" && <div className={cx("skeleton", s.loadbar)} aria-hidden="true" />}
              {dp ? <PathChain path={dp.path} evidence={decidingEvent(dp.evidence)} /> : <p className="t-footnote">{notes[0] ?? audit.decision.title}</p>}
            </div>
          )}
          {ready && notes.length > 0 && <div className={s.notes}><p>{notes[0]}</p></div>}
        </div>
        {onExpand && (
          <button type="button" className={s.expand} onClick={onExpand} aria-label={`Explore ${audit.decision.id} in 3D`} />
        )}
      </figure>
    );
  }

  return (
    <figure ref={rootRef} className={cx(s.fig, night && s.night)} aria-label={label}>
      <div className={s.bar}>
        {hasEvidence ? (
          <Segmented label="Evidence shown" value={decidingOnly ? "deciding" : "all"} onChange={v => setDecidingOnly(v === "deciding")}
            options={[["all", "All evidence"], ["deciding", "Deciding evidence"]]} />
        ) : <span />}
        {ready && (
          <div className={s.tools}>
            <button type="button" className={cx("btn ghost small", s.icon)} aria-label="Zoom out" onClick={() => viewRef.current?.zoomBy(1 / 1.25)}>−</button>
            <button type="button" className={cx("btn ghost small", s.icon)} aria-label="Zoom in" onClick={() => viewRef.current?.zoomBy(1.25)}>+</button>
            <button type="button" className="btn ghost small" onClick={() => viewRef.current?.reset()}>Reset</button>
          </div>
        )}
      </div>

      <div className={s.body}>
        <div ref={stageRef} className={cx(s.stage, retired && s.retired)} style={{ height: h }} onMouseLeave={() => setHovered(null)}>
          {scene}
          {ready && <Callouts store={store} parts={parts} drawing={drawing} audit={audit} compact={compact} active={active} onHover={setHovered} />}
          {!ready && (
            <div className={s.fallback}>
              {gl === "none" && <p className="t-footnote">The 3D drawing needs WebGL. Here are the same paths as rows.</p>}
              {gl !== "none" && <div className={cx("skeleton", s.loadbar)} aria-hidden="true" />}
              <Chains audit={audit} />
            </div>
          )}
          {gate && (
            <div className={s.stamp}>
              <span className={s.stampRow}><span className={s.stampLabel}>Agent gate</span><GateBadge gate={gate.gate} /></span>
              {gate.snapshot?.digest && !compact && (
                <span className={s.digest} title="Snapshot digest of the graph the gate read"><span className="id">{gate.snapshot.digest}</span></span>
              )}
            </div>
          )}
          {notes.length > 0 && <div className={s.notes}>{notes.map(n => <p key={n}>{n}</p>)}</div>}
          {ready && fine && <span className={s.orbitHint} aria-hidden="true">Drag to turn</span>}
        </div>

        <div className={s.side}>
          <Group header="Parts" label="Parts of the drawing" onSurface>
            {parts.map(p => {
              const t = partText(p, audit);
              return (
                <div key={p.key} className={cx(s.partRow, activeKey === p.key && s.partOn)}
                  onMouseEnter={() => setHovered(p.key)} onMouseLeave={() => setHovered(null)}
                  onFocus={() => setHovered(p.key)} onBlur={() => setHovered(null)}>
                  <Row leading={<Marker part={p} />} title={t.title} clip chevron={false} selected={pinned === p.key} onClick={() => pick(p.key)}
                    subtitle={<><span className="id">{t.id}</span> · {t.word}</>} />
                </div>
              );
            })}
          </Group>
          <div className={s.detailWrap} aria-live="polite">
            {activePart ? <Detail part={activePart} audit={audit} />
              : <p className="t-footnote">Tap a part, or point at it, to trace its path back to the decision.</p>}
          </div>
          {audit.premises.length > 0 && <Group header="Line styles" label="Line styles" onSurface>
            {LEGEND.filter(([k]) => present.has(k)).map(([k, t]) => (
              <div key={k} className={s.styleRow}><Swatch kind={k} /><span>{t}</span></div>
            ))}
          </Group>}
        </div>
      </div>
      {ready && <div className="sr-only"><Chains audit={audit} /></div>}
    </figure>
  );
}
