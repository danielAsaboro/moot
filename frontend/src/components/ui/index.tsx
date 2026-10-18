"use client";
// Shared calm primitives, imported from "@/components/ui".
// The older exports keep their names and props (VerdictBadge, GateBadge, StateTag, PathChain, decidingEvent, SectionHead,
// Wordmark, Docket, ThemeToggle, cx) so copied components still work; they now render the calm style.
import { useEffect, useId, useRef, useState, type ReactNode, type MouseEventHandler } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import s from "./ui.module.css";
import type { GateDecision, PathNode, PremiseState, Verdict, EvidenceEvent } from "@/lib/types";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

/* ---------- words ---------- */
export const VERDICT_WORD: Record<Verdict, string> = {
  MOOT: "Moot", HOLDS: "Holds", DISPUTED: "Disputed", UNDOCUMENTED: "Undocumented", RETIRED: "Retired",
  NOT_YET: "Not yet decided", NOT_IN_GRAPH: "Not in the graph",
};
export const GATE_WORD: Record<GateDecision, string> = { ALLOW: "Allow", DENY: "Deny", REVALIDATE: "Revalidate" };
export const STATE_WORD: Record<PremiseState, string> = {
  holds: "Holds", expired: "Expired", disputed: "Disputed", unchecked: "Unchecked", unevidenced: "Unverified",
};

type Tone = "moot" | "holds" | "disputed" | "neutral";
const VERDICT_TONE: Record<Verdict, Tone> = { MOOT: "moot", HOLDS: "holds", DISPUTED: "disputed", UNDOCUMENTED: "neutral", RETIRED: "neutral", NOT_YET: "neutral", NOT_IN_GRAPH: "neutral" };
const GATE_TONE: Record<GateDecision, Tone> = { DENY: "moot", ALLOW: "holds", REVALIDATE: "disputed" };
const STATE_TONE: Record<PremiseState, Tone> = { expired: "moot", holds: "holds", disputed: "disputed", unchecked: "neutral", unevidenced: "neutral" };

/* ---------- pills ---------- */
export function Pill({ tone = "neutral", size = "sm", solid = false, dashed = false, children, title, className }:
  { tone?: Tone; size?: "sm" | "md" | "lg"; solid?: boolean; dashed?: boolean; children: ReactNode; title?: string; className?: string }) {
  const solidCls = solid ? (tone === "moot" ? s.solid : tone === "holds" ? s.solidHolds : tone === "disputed" ? s.solidDisputed : s.solidNeutral) : s[tone];
  return <span className={cx(s.pill, size !== "sm" && s[size], dashed ? s.dashed : solidCls, className)} title={title}>{children}</span>;
}

/** Verdict as a tinted pill in sentence case. `fill` = solid (the one prominent verdict on a screen). */
export function VerdictBadge({ verdict, fill = false, size = "sm", className }: { verdict: Verdict; fill?: boolean; size?: "sm" | "md" | "lg"; className?: string }) {
  return <Pill tone={VERDICT_TONE[verdict]} solid={fill} dashed={verdict === "NOT_YET"} size={size} className={className}>{VERDICT_WORD[verdict]}</Pill>;
}

/** The agent gate's answer as a pill: Allow / Deny / Revalidate. */
export function GateBadge({ gate, title, size = "sm", className }: { gate: GateDecision; title?: string; size?: "sm" | "md" | "lg"; className?: string }) {
  return <Pill tone={GATE_TONE[gate]} size={size} title={title} className={className}>{GATE_WORD[gate]}</Pill>;
}

export function StateTag({ state }: { state: PremiseState }) {
  return <Pill tone={STATE_TONE[state]}>{STATE_WORD[state]}</Pill>;
}

/* ---------- path chain ---------- */
const NODE_WORD: Record<string, string> = { Decision: "Decision", Premise: "Reason", Evidence: "Evidence" };

/** Decision → Reason → … ← Evidence, every node from the rows. Arrows travel with the node after them. */
export function PathChain({ path, evidence, showIds = false }: { path: PathNode[]; evidence?: EvidenceEvent | null; showIds?: boolean }) {
  const nodes = path.map(n => (
    <div key={n.id} className={cx(s.node, s[n.label])}><span className={s.nl}>{NODE_WORD[n.label] ?? n.label}{showIds ? ` · ${n.id}` : ""}</span>{n.title}</div>
  ));
  return (
    <div className={s.path}>
      {nodes.map((n, i) => (i ? <span key={i} className={s.step}><span className={s.arrow}>→</span>{n}</span> : n))}
      {evidence && (
        <span className={s.step}><span className={s.arrow}>←</span>
          <div className={cx(s.node, evidence.rel === "CONTRADICTS" ? s.contra : s.sup)}>
            <span className={s.nl}>{evidence.rel === "CONTRADICTS" ? "Contradicts" : "Supports"} · {evidence.at}</span>{evidence.title}
          </div>
        </span>
      )}
    </div>
  );
}

/** The latest event that decides a premise's state (the contradiction if it is newest, else the newest support). */
export function decidingEvent(evidence: EvidenceEvent[]): EvidenceEvent | null {
  const c = [...evidence].filter(e => e.rel === "CONTRADICTS").pop();
  const sup = [...evidence].filter(e => e.rel === "SUPPORTS").pop();
  return c && (!sup || sup.at < c.at) ? c : (sup ?? c ?? null);
}

/* ---------- headings ---------- */
/** apple.com section head: small eyebrow, large serif title, optional lead. `title` may include a muted second clause via `muted`. */
export function SectionHead({ eyebrow, title, muted, children, id, center = false, size = "display" }:
  { eyebrow?: string; title: string; muted?: string; children?: ReactNode; id?: string; center?: boolean; size?: "hero" | "display" | "large" }) {
  const Tag = size === "hero" ? "h1" : "h2";
  return (
    <div className={cx(s.shead, center && s.center)} id={id}>
      {eyebrow && <div className="t-eyebrow">{eyebrow}</div>}
      <Tag className={`t-${size}`} style={{ margin: 0 }}>{title}{muted && <> <span style={{ color: "var(--label-3)" }}>{muted}</span></>}</Tag>
      {children && <p className="t-lead">{children}</p>}
    </div>
  );
}

export function Wordmark({ size = 40, as: Tag = "span" }: { size?: number; as?: "span" | "h1" | "div" }) {
  return <Tag className={s.wordmark} style={{ fontSize: size }}>M<s>oo</s>t</Tag>;
}

/** Stat row (the docket, calmer): small label over a value. Up to `columns` per row; narrower panes wrap. */
export function Docket({ items, columns = 4, className }: { items: [string, ReactNode][]; columns?: number; className?: string }) {
  const cols = Math.min(columns, items.length || 1);
  return (
    <dl className={cx(s.docket, className)}
      style={{ gridTemplateColumns: `repeat(auto-fit, minmax(max(7rem, calc((100% - ${(cols - 1) * 24}px) / ${cols})), 1fr))` }}>
      {items.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
    </dl>
  );
}

export function ThemeToggle() {
  const [mode, setMode] = useState<"light" | "dark" | null>(null);
  useEffect(() => {
    const t = document.documentElement.dataset.theme as "light" | "dark" | undefined;
    setMode(t ?? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  }, []);
  const flip = () => {
    const next = mode === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("moot-theme", next); } catch { /* storage blocked */ }
    setMode(next);
  };
  return <button type="button" className={s.toggle} onClick={flip} aria-label="Toggle dark mode">{mode === "dark" ? "Light" : "Dark"}</button>;
}

/* ---------- iOS building blocks ---------- */
/** Inset grouped list. Put <Row>s inside. `onSurface` when the group sits inside a card. */
export function Group({ header, footer, onSurface = false, children, className, label }:
  { header?: ReactNode; footer?: ReactNode; onSurface?: boolean; children: ReactNode; className?: string; label?: string }) {
  return (
    <section className={cx(s.group, className)} aria-label={label}>
      {header && <div className={s.groupHead}>{header}</div>}
      <div className={cx(s.groupBody, onSurface && s.onSurface)}>{children}</div>
      {footer && <div className={s.groupFoot}>{footer}</div>}
    </section>
  );
}

/** One list row: title, optional subtitle, leading and trailing slots, chevron when it navigates.
 *  Pass `href` (internal, via next/link) or `onClick`; otherwise it renders as static content. */
export function Row({ title, subtitle, leading, trailing, href, onClick, chevron, inset = false, selected = false, clip = false, ariaLabel }:
  { title: ReactNode; subtitle?: ReactNode; leading?: ReactNode; trailing?: ReactNode; href?: string; onClick?: MouseEventHandler;
    chevron?: boolean; inset?: boolean; selected?: boolean; clip?: boolean; ariaLabel?: string }) {
  const cls = cx(s.row, inset && s.inset, selected && s.selected);
  const body = (
    <>
      {leading}
      <span className={s.rowMain}>
        <span className={cx(s.rowTitle, clip && s.clip)}>{title}</span>
        {subtitle && <span className={s.rowSub}>{subtitle}</span>}
      </span>
      {trailing}
      {(chevron ?? Boolean(href || onClick)) && <span className={s.chev} aria-hidden="true">›</span>}
    </>
  );
  if (href) return <Link href={href} className={cls} aria-label={ariaLabel} aria-current={selected ? "true" : undefined}>{body}</Link>;
  if (onClick) return <button type="button" className={cls} onClick={onClick} aria-label={ariaLabel} aria-pressed={selected}>{body}</button>;
  return <div className={cls}>{body}</div>;
}

export function Card({ children, className, flat = false, as: Tag = "div" }: { children: ReactNode; className?: string; flat?: boolean; as?: "div" | "section" | "article" | "figure" }) {
  return <Tag className={cx(s.card, flat && s.flat, className)}>{children}</Tag>;
}

/** Segmented control (role=tablist). Arrow keys move between segments. */
export function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: [T, string][]; onChange: (v: T) => void; label: string }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const idx = options.findIndex(([v]) => v === value);
  const move = (d: number) => {
    const n = (idx + d + options.length) % options.length;
    onChange(options[n][0]); refs.current[n]?.focus();
  };
  return (
    <div role="tablist" aria-label={label} className={s.seg}
      onKeyDown={e => { if (e.key === "ArrowRight") { e.preventDefault(); move(1); } if (e.key === "ArrowLeft") { e.preventDefault(); move(-1); } }}>
      {options.map(([v, l], i) => (
        <button key={v} ref={el => { refs.current[i] = el; }} type="button" role="tab" aria-selected={v === value} tabIndex={v === value ? 0 : -1} onClick={() => onChange(v)}>{l}</button>
      ))}
    </div>
  );
}

export function SearchField({ value, onChange, onSubmit, placeholder, label, inputRef, onFocus, onBlur, disabled }:
  { value: string; onChange: (v: string) => void; onSubmit?: () => void; placeholder?: string; label: string;
    inputRef?: React.Ref<HTMLInputElement>; onFocus?: () => void; onBlur?: () => void; disabled?: boolean }) {
  return (
    <form className={s.search} role="search" onSubmit={e => { e.preventDefault(); onSubmit?.(); }}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
      <input ref={inputRef} type="search" value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} aria-label={label}
        onFocus={onFocus} onBlur={onBlur} disabled={disabled} />
    </form>
  );
}

/** Summary card (Health / Fitness): label, big number, optional foot (a sparkline or a line of text). */
export function StatCard({ label, value, tone = "neutral", foot, on = false, onClick, ariaLabel }:
  { label: string; value: ReactNode; tone?: Tone; foot?: ReactNode; on?: boolean; onClick?: () => void; ariaLabel?: string }) {
  const color = tone === "moot" ? "var(--moot-ink)" : tone === "holds" ? "var(--holds-ink)" : tone === "disputed" ? "var(--disputed-ink)" : "var(--label-2)";
  const inner = (<><span className={s.statLabel} style={{ color }}>{label}</span><span className={s.statValue}>{value}</span>{foot && <span className={s.statFoot}>{foot}</span>}</>);
  return onClick
    ? <button type="button" className={cx(s.stat, on && s.on)} onClick={onClick} aria-pressed={on} aria-label={ariaLabel}>{inner}</button>
    : <div className={s.stat}>{inner}</div>;
}

/** A sheet: a scoped task over the current view (Apple HIG). Escape or Cancel closes it; focus moves in and back.
 *  Rendered into document.body, so a sticky or blurred ancestor (which creates a containing block) cannot trap it. */
export function Sheet({ open, title, onClose, children, cancelLabel = "Cancel", action }:
  { open: boolean; title: string; onClose: () => void; children: ReactNode; cancelLabel?: string; action?: ReactNode }) {
  const id = useId();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    box.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow; document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = overflow; prev?.focus?.(); };
  }, [open, onClose]);
  if (!open || typeof document === "undefined") return null;
  return createPortal(
    <div className={s.scrim} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={box} className={s.sheet} role="dialog" aria-modal="true" aria-labelledby={id} tabIndex={-1}>
        <div className={s.grabber} aria-hidden="true" />
        <div className={s.sheetBar}>
          <button type="button" className={`btn plain ${s.left}`} onClick={onClose}>{cancelLabel}</button>
          <h2 id={id}>{title}</h2>
          <span className={s.right}>{action}</span>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

export { cx };
