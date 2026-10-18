"use client";
// One reason as a grouped-list row: the reason, a grey line (where it sits and what decides it), its state pill.
// Tap to expand: the path from the decision to it, its dated evidence (each opens its exhibit card), and the owner
// ruling for a reason nobody can vouch for.
import { useId, useState, type CSSProperties } from "react";
import { PathChain, Pill, StateTag, cx, decidingEvent } from "@/components/ui";
import type { Owner, Premise } from "@/lib/types";
import { longDate } from "@/lib/format";
import RulingControl from "./RulingControl";
import s from "./Premise.module.css";

const RULABLE = new Set(["disputed", "unchecked", "unevidenced"]);

export interface ExhibitRef { n: number; anchor: string; rel: string; at: string; id: string }

export const exhibitLabel = (n: number) => String(n);

/** Scroll to an exhibit card and focus it. */
function showExhibit(anchor: string) {
  const el = document.getElementById(anchor);
  if (!el) return;
  el.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  el.querySelector<HTMLElement>("button")?.focus({ preventScroll: true });
}

/** "Stated reason", "The reason behind it", "3 reasons down". */
export function premisePlace(hops: number): string {
  return hops <= 1 ? "Stated reason" : hops === 2 ? "The reason behind it" : `${hops - 1} reasons down`;
}

/** What decides the state, in a few words: "contradicted 2 Mar 2026", "no evidence either way". */
export function premiseStatus(p: Premise): string {
  const ev = decidingEvent(p.evidence);
  const last = (rel: string) => [...p.evidence].filter(e => e.rel === rel).sort((a, b) => a.at.localeCompare(b.at)).pop();
  switch (p.state) {
    case "expired": return ev ? `contradicted ${longDate(ev.at)}` : "contradicted";
    case "disputed": {
      const c = last("CONTRADICTS"), sup = last("SUPPORTS");
      return c && sup ? `contradicted ${longDate(c.at)}, re-affirmed ${longDate(sup.at)}` : "contradicted and re-affirmed";
    }
    case "holds": return ev ? `supported ${longDate(ev.at)}` : "nothing stands against it";
    case "unchecked": return "could not be checked";
    default: return "no evidence either way";
  }
}

export default function PremiseBlock({ premise: p, exhibits, decisionId, asOf, owner, onChanged }: {
  premise: Premise; exhibits: ExhibitRef[]; decisionId: string; asOf: string; owner: Owner | null; onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const panel = useId();
  const sorted = [...p.evidence].sort((a, b) => a.at.localeCompare(b.at));
  const refFor = (id: string, rel: string, at: string) => exhibits.find(x => x.id === id && x.rel === rel && x.at === at);

  return (
    <div className={cx(s.item, p.hops > 1 && s.inset)} style={p.hops > 2 ? ({ "--indent": `${16 + 20 * Math.min(p.hops - 1, 3)}px` } as CSSProperties) : undefined}>
      <button type="button" className={s.row} aria-expanded={open} aria-controls={panel} onClick={() => setOpen(o => !o)}>
        <span className={s.main}>
          <span className={s.title}>{p.text}</span>
          <span className={s.sub}>{premisePlace(p.hops)} · {premiseStatus(p)}</span>
        </span>
        <StateTag state={p.state} />
        <span className={cx(s.chev, open && s.chevOpen)} aria-hidden="true">›</span>
      </button>

      <div id={panel} hidden={!open} className={s.detail}>
        <PathChain path={p.path} evidence={decidingEvent(p.evidence)} />

        {sorted.length > 0 && (
          <ul className={s.events} aria-label="Dated evidence">
            {sorted.map(ev => {
              const ref = refFor(ev.id, ev.rel, ev.at);
              const body = (
                <>
                  <Pill tone={ev.rel === "CONTRADICTS" ? "moot" : "holds"}>{ev.ruling ? "Ruling · " : ""}{ev.rel === "CONTRADICTS" ? "Contradicts" : "Supports"}</Pill>
                  <span className={s.evMain}>
                    <span className={s.evTitle}>{ev.title}</span>
                    <span className={s.evSub}><span className="id">{ev.id}</span> · {longDate(ev.at)}{ev.author ? ` · ${ev.author}` : ""}</span>
                  </span>
                </>
              );
              return (
                <li key={`${ev.id}-${ev.rel}-${ev.at}`}>
                  {ref ? (
                    <button type="button" className={s.event} onClick={() => showExhibit(ref.anchor)}
                      aria-label={`Show exhibit ${exhibitLabel(ref.n)}: ${ev.id}, ${ev.rel === "CONTRADICTS" ? "contradicts" : "supports"}, ${longDate(ev.at)}`}>
                      {body}<span className={s.exLink}>Exhibit {exhibitLabel(ref.n)}</span>
                    </button>
                  ) : <div className={s.event}>{body}</div>}
                </li>
              );
            })}
          </ul>
        )}

        {p.evidence.length === 0 && (
          <p className={s.note}>{p.unchecked ? <><span className="lead-in">Could not be checked.</span> {p.unchecked}.</> : "No dated evidence touches this reason yet."}</p>
        )}
        {p.contradicted_before_decision && (
          <p className={s.note}><span className="lead-in">Already false when decided.</span> The contradiction predates the decision.</p>
        )}
        {RULABLE.has(p.state) && (
          <div className={s.ruleRow}>
            <RulingControl decisionId={decisionId} premise={p} asOf={asOf} owner={owner} onChanged={onChanged} />
            <span className="t-footnote">Only the owner can settle this one.</span>
          </div>
        )}
      </div>
    </div>
  );
}
