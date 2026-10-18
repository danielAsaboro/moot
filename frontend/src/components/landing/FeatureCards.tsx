"use client";
// The six example cards that lift out of the feature tiles. Each card reads real rows; nothing here is typed in.
import { useApi } from "@/lib/useApi";
import { longDate, plural } from "@/lib/format";
import { GateBadge, PathChain, VerdictBadge, decidingEvent } from "@/components/ui";
import type { Audit, EvidenceEvent } from "@/lib/types";
import {
  TRAVEL_FROM, idle, loadD01, loadD01Shallow, loadD07Now, loadD07Then, loadGate, loadOrphans, loadWhatIf,
} from "./FeatureData";
import s from "./Features.module.css";

type CardProps = { armed: boolean };

/** Fetch only once the tile is armed (scrolled into view, hovered or focused). */
const lazy = <T,>(armed: boolean, load: () => Promise<T>) => () => (armed ? load() : idle<T>());

function Skel() {
  return (
    <div className={s.skel} aria-label="Loading the example" role="status">
      <div className="skeleton" /><div className="skeleton" /><div className="skeleton" />
    </div>
  );
}

function Failed({ error }: { error: string }) {
  return <p className={s.err}>Could not load this example: {error}</p>;
}

/** The first premise that breaks the decision, with the event that decides it. */
function broken(a: Audit): { path: Audit["premises"][number]["path"]; ev: EvidenceEvent | null; hops: number; id: string } | null {
  const p = a.premises.find(x => x.state === "expired") ?? a.premises.find(x => x.state === "disputed");
  return p ? { path: p.path, ev: decidingEvent(p.evidence), hops: p.hops, id: p.id } : null;
}

const Id = ({ children }: { children: string }) => <span className={s.id}>{children}</span>;

export function PathCard({ armed }: CardProps) {
  const { data, error } = useApi(lazy(armed, loadD01), [armed]);
  if (error) return <Failed error={error} />;
  if (!data) return <Skel />;
  const a = data.audit;
  const b = broken(a);
  return (
    <>
      <div className={s.cardHead}><Id>{a.decision.id}</Id><span className={s.cardTitle}>{a.decision.title}</span><VerdictBadge verdict={a.verdict} /></div>
      {/* the header names the decision, so the chain starts at its first reason */}
      {b && <PathChain path={b.path.slice(1)} evidence={b.ev} />}
    </>
  );
}

export function TimeCard({ armed }: CardProps) {
  const then = useApi(lazy(armed, loadD07Then), [armed]);
  const now = useApi(lazy(armed, loadD07Now), [armed]);
  const error = then.error ?? now.error;
  if (error) return <Failed error={error} />;
  if (!then.data || !now.data) return <Skel />;
  const a0 = then.data.audit, a1 = now.data.audit;
  // the event dated after the first view that decides the broken premise now
  const b = broken(a1);
  const changer = b?.ev && b.ev.at > TRAVEL_FROM ? b.ev : null;
  return (
    <>
      <div className={s.cardHead}><Id>{a1.decision.id}</Id><span className={s.cardTitle}>{a1.decision.title}</span></div>
      <dl className={s.rows}>
        <div><dt>as of {longDate(a0.as_of)}</dt><dd><VerdictBadge verdict={a0.verdict} /></dd></div>
        <div><dt>as of {longDate(a1.as_of)}</dt><dd><VerdictBadge verdict={a1.verdict} /></dd></div>
      </dl>
      {changer && a0.verdict !== a1.verdict && (
        <p className={s.note}><Id>{changer.id}</Id> {changer.rel.toLowerCase()} the reason on {longDate(changer.at)}: {changer.title}</p>
      )}
    </>
  );
}

export function DepthCard({ armed }: CardProps) {
  const shallow = useApi(lazy(armed, loadD01Shallow), [armed]);
  const deep = useApi(lazy(armed, loadD01), [armed]);
  const error = shallow.error ?? deep.error;
  if (error) return <Failed error={error} />;
  if (!shallow.data || !deep.data) return <Skel />;
  const a1 = shallow.data.audit, a4 = deep.data.audit;
  const b = broken(a4);
  return (
    <>
      <div className={s.cardHead}><Id>{a4.decision.id}</Id><span className={s.cardTitle}>{a4.decision.title}</span></div>
      <dl className={s.rows}>
        <div><dt>depth {a1.depth}</dt><dd><VerdictBadge verdict={a1.verdict} /></dd></div>
        <div><dt>depth {a4.depth}</dt><dd><VerdictBadge verdict={a4.verdict} /></dd></div>
      </dl>
      {b && b.ev && (
        <p className={s.note}>The broken reason sits {plural(b.hops, "hop")} down; <Id>{b.ev.id}</Id> {b.ev.rel.toLowerCase()} it.</p>
      )}
    </>
  );
}

export function GateCard({ armed }: CardProps) {
  const { data, error } = useApi(lazy(armed, loadGate), [armed]);
  if (error) return <Failed error={error} />;
  if (!data) return <Skel />;
  const r = data.reasons[0];
  return (
    <>
      <div className={s.cardHead}><Id>{data.decision_id}</Id><span className={s.cardTitle}>{data.title ?? ""}</span><GateBadge gate={data.gate} /></div>
      {r && <p className={s.note}>{r.text}</p>}
      {r?.evidence && <p className={s.meta}>evidence <Id>{r.evidence}</Id> · as of {longDate(data.as_of)}</p>}
    </>
  );
}

export function WhatIfCard({ armed }: CardProps) {
  const { data, error } = useApi(lazy(armed, loadWhatIf), [armed]);
  if (error) return <Failed error={error} />;
  if (!data) return <Skel />;
  if (!data.found || !data.premise) return <p className={s.note}>{data.answer ?? "No reason in the graph matches that question."}</p>;
  const fall = (data.decisions ?? []).filter(d => d.flips);
  return (
    <>
      <p className={s.quote}>&ldquo;{data.premise.text}&rdquo; stops holding:</p>
      <p className={s.big}><span className="tabular">{data.would_fall ?? fall.length}</span> {(data.would_fall ?? fall.length) === 1 ? "decision falls" : "decisions fall"}</p>
      <div className={s.ids}>{fall.map(d => <span key={d.id} className={s.flip}><Id>{d.id}</Id><VerdictBadge verdict={d.before} /><span aria-hidden="true">→</span><span className="sr-only">becomes</span><VerdictBadge verdict={d.after} /></span>)}</div>
    </>
  );
}

export function HandoverCard({ armed }: CardProps) {
  const { data, error } = useApi(lazy(armed, loadOrphans), [armed]);
  if (error) return <Failed error={error} />;
  if (!data) return <Skel />;
  if (!data.groups.length) return <p className={s.note}>Every decision has an owner as of {longDate(data.as_of)}.</p>;
  return (
    <ul className={s.hand}>
      {data.groups.map(g => (
        <li key={g.person.id}>
          <span className={s.who}>{g.person.name} left {longDate(g.person.left)}</span>
          <span className={s.meta}>{plural(g.decisions.length, "decision")}: {g.decisions.map(d => d.id).join(", ")}</span>
          <span className={s.meta}>{g.successor ? <>routed to {g.successor.name}, {g.successor.role}</> : "no one to route to"}</span>
        </li>
      ))}
    </ul>
  );
}

