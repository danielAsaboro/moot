"use client";
// How it works, on paper: the story of D01 told from its own rows (left) beside the record chain that proves it (right).
import { useApi } from "@/lib/useApi";
import type { Audit } from "@/lib/types";
import { SectionHead, VerdictBadge } from "@/components/ui";
import { REF_DATE, loadD01 } from "./FeatureData";
import HeroRecords, { pickPremise } from "./HeroRecords";
import s from "./HowItWorks.module.css";

const DEPTH = 4;

/** "2026-03-02" -> "2 March 2026" */
const fullDate = (iso: string) => {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
};

/** Lower-case the first letter of a sentence fragment, unless the first word is an acronym ("CSV", "API"). */
export const lowerFirst = (t: string) => (/^[A-Z][a-z]/.test(t) ? t[0].toLowerCase() + t.slice(1) : t);

/** "Raise the gateway limit" -> "raised the gateway limit". Null when the first word is not a plain verb we know. */
function pastTense(title: string): string | null {
  const m = /^([A-Z][a-z]+)\b(.*)$/.exec(title);
  if (!m) return null;
  const w = m[1].toLowerCase();
  const irregular: Record<string, string> = { drop: "dropped", stop: "stopped", set: "set", cut: "cut", split: "split", shut: "shut", move: "moved" };
  const verbs = ["raise", "lower", "remove", "replace", "add", "increase", "decrease", "deprecate", "retire", "migrate", "switch",
    "enable", "disable", "change", "allow", "upgrade", "downgrade", "lift", "end", "extend", "introduce", "adopt", "launch", "sunset"];
  let past = irregular[w];
  if (!past && verbs.includes(w)) past = w.endsWith("e") ? `${w}d` : `${w}ed`;
  return past ? `${past}${m[2]}` : null;
}

/** The story paragraph, built only from the audit rows. */
function Story({ audit }: { audit: Audit }) {
  const pick = pickPremise(audit.premises);
  const p = pick?.premise;
  const ev = pick?.event;
  const contra = ev?.rel === "CONTRADICTS";
  const did = ev ? pastTense(ev.title) : null;
  return (
    <p className={`t-lead ${s.story}`}>
      <span className="lead-in">{audit.decision.title}.</span>{" "}
      {p && <>It rested on {p.hops > 1 ? "a deeper reason" : "one reason"}: {lowerFirst(p.text)}.{" "}</>}
      {ev && contra && (did
        ? <>On {fullDate(ev.at)}, <span className="id">{ev.id}</span> {did}.{" "}</>
        : <>On {fullDate(ev.at)}, <span className="id">{ev.id}</span> said otherwise: {lowerFirst(ev.title)}.{" "}</>)}
      {ev && !contra && <>On {fullDate(ev.at)}, <span className="id">{ev.id}</span> confirmed it.{" "}</>}
      {audit.verdict === "MOOT" && !audit.superseded_by && <>Nobody touched the rule.</>}
    </p>
  );
}

export default function HowItWorks() {
  const { data, error } = useApi(loadD01, []);
  const audit = data?.audit;

  return (
    <section id="how" className={s.section} aria-labelledby="how-title">
      <div className={s.inner}>
        <div className={s.copy}>
          <SectionHead eyebrow="How it works" title="Every rule has a reason." muted="Reasons expire." id="how-title" />
          {audit ? (
            <>
              <Story audit={audit} />
              <div className={s.verdict}>
                <span className={s.so}>So the rule is</span>
                <VerdictBadge verdict={audit.verdict} fill size="lg" />
              </div>
            </>
          ) : error ? (
            <p className="t-lead">The example could not load. {error}</p>
          ) : (
            <div className={s.storySkel} aria-busy="true" aria-label="Loading the example">
              <span className="skeleton" /><span className="skeleton" /><span className="skeleton" />
            </div>
          )}
        </div>
        <HeroRecords data={data} error={error} asOf={REF_DATE} depth={DEPTH} />
      </div>
    </section>
  );
}
