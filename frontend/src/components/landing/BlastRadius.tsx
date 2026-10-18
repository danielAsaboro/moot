"use client";
// The red band: one broken reason and every rule that rests on it. Left, the line drawing of D01's audit with the
// decisions that share its expired reason; right, the headline whose numbers come from the same response.
import { useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/useApi";
import { loadD01 } from "./FeatureData";
import HowDrawing from "./HowDrawing";
import s from "./BlastRadius.module.css";

const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];
const word = (n: number) => WORDS[n] ?? String(n);
const Cap = (t: string) => t[0].toUpperCase() + t.slice(1);

/** Wide drawing (side column) once its own box is at least this wide; measured, so it follows the layout. */
function useWideBox(min = 470) {
  const ref = useRef<HTMLDivElement>(null);
  const [wide, setWide] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const on = () => setWide(el.clientWidth >= min);
    on();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(on);
    ro.observe(el);
    return () => ro.disconnect();
  }, [min]);
  return { ref, wide };
}

export default function BlastRadius() {
  const { data, error } = useApi(loadD01, []);
  const { ref, wide } = useWideBox();
  const audit = data?.audit;

  const brokenIds = new Set((audit?.premises ?? []).filter(p => p.state === "expired" || p.state === "disputed").map(p => p.id));
  const also: { id: string; title: string }[] = [];
  for (const im of data?.impact ?? []) {
    if (!brokenIds.has(im.premise.id)) continue;
    for (const d of im.decisions) if (d.id !== audit?.decision.id && !also.some(a => a.id === d.id)) also.push(d);
  }
  const reasons = brokenIds.size;
  const rules = 1 + also.length;

  const title = !audit ? "One reason breaks. Every rule on it falls."
    : reasons === 0 ? "Every reason still holds."
    : `${Cap(word(reasons))} ${reasons === 1 ? "reason breaks" : "reasons break"}. ${Cap(word(rules))} ${rules === 1 ? "rule falls" : "rules fall"}.`;
  const quoted = also.map(a => `“${a.title}”`);
  const list = quoted.length <= 1 ? quoted.join("") : `${quoted.slice(0, -1).join(", ")} and ${quoted[quoted.length - 1]}`;

  return (
    <section className={s.band} aria-labelledby="blast-title">
      <div className={s.inner}>
        <figure className={s.figure} ref={ref}>
          {audit ? (
            <>
              <HowDrawing audit={audit} impact={data?.impact} wide={wide} />
              <figcaption className={s.caption}>
                Dashed: the reason that expired{also.length ? " and the rules that rest on it" : ""}. Filled: the evidence that contradicts it.
              </figcaption>
            </>
          ) : error ? (
            <p className={s.msg}>The drawing could not load. {error}</p>
          ) : (
            <div className={s.skel} aria-busy="true" aria-label="Loading the drawing"><span /><span /><span /><span /></div>
          )}
        </figure>

        <div className={s.copy}>
          <div className={s.eyebrow}>The blast radius</div>
          <h2 id="blast-title" className={`t-display ${s.title}`}>{title}</h2>
          {audit && reasons > 0 && (
            <p className={s.body}>
              {also.length > 0 && <>The same reason also holds up {also.length === 1 ? "one more rule" : `${word(also.length)} more rules`}: {list}. </>}
              Moot follows every path back to the broken reason, so you can fix {rules === 1 ? "it" : rules === 2 ? "both" : `all ${word(rules)}`} at once.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
