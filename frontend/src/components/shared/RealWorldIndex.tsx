"use client";
// The public ADRs as an inset grouped list: title, one grey line that says why, the verdict pill.
// Compact rows link out to the record on GitHub; full rows open in place to show the quote, the retiring document
// and every unwritten reason with the check that decided it.
import { useId, useState, type ReactNode } from "react";
import type { GateDecision, RealWorldDecision, RealWorldResponse, Verdict } from "@/lib/types";
import { GateBadge, Group, StateTag, VerdictBadge, cx, decidingEvent } from "@/components/ui";
import { longDate } from "@/lib/format";
import s from "./RealWorld.module.css";

const RANK: Partial<Record<Verdict, number>> = { MOOT: 0, DISPUTED: 1, RETIRED: 2, UNDOCUMENTED: 3, HOLDS: 4 };
const GATE_RANK: Record<GateDecision, number> = { DENY: 0, REVALIDATE: 1, ALLOW: 2 };
/** The gate answer a verdict implies; the gate pill shows only when the gate says something else. */
const IMPLIED: Partial<Record<Verdict, GateDecision>> = { MOOT: "DENY", RETIRED: "DENY", HOLDS: "ALLOW" };

/** MOOT first, then retired, then the rest; within a verdict, the gate's most cautious answer first. Stable otherwise. */
export function sortRecords(ds: RealWorldDecision[]): RealWorldDecision[] {
  return ds.map((d, i) => ({ d, i })).sort((a, b) =>
    (RANK[a.d.verdict] ?? 9) - (RANK[b.d.verdict] ?? 9) || GATE_RANK[a.d.gate] - GATE_RANK[b.d.gate] || a.i - b.i).map(x => x.d);
}

const shortRepo = (repo: string) => repo.split("/").pop() || repo;
/** "last commit on 2020-08-19" -> "last commit on 19 Aug 2020". Only reformats dates already in the text. */
const prettyDates = (t: string) => t.replace(/\b\d{4}-\d{2}-\d{2}\b/g, m => longDate(m));
/** The tool a reason is about, from its id (p_<tool>_<check>). */
const toolOf = (d: RealWorldDecision, reasonId: string) => d.tools.find(t => reasonId.startsWith(`p_${t.id}_`))?.name ?? null;

/** The one grey line under the title: repository, then the fact that decided the verdict. */
function why(d: RealWorldDecision): string {
  const repo = shortRepo(d.repo);
  if (d.retired) {
    const doc = d.retired.title.split(":")[0];
    return d.retired.title.includes(":")
      ? `${repo} · retired by ${doc} on ${longDate(d.retired.date)}`
      : `${repo} · ${doc} on ${longDate(d.retired.date)}`;
  }
  const broken = d.reasons.find(r => r.state === "expired" || r.state === "disputed");
  if (broken) {
    const ev = decidingEvent(broken.evidence);
    const tool = toolOf(d, broken.id);
    const fact = ev ? prettyDates(ev.quote || ev.title) : broken.text;
    return `${repo} · ${tool ? `${tool}: ` : ""}${fact}`;
  }
  const unchecked = d.reasons.filter(r => r.state === "unchecked");
  if (unchecked.length) {
    const tool = toolOf(d, unchecked[0].id);
    return `${repo} · ${tool ? `${tool}: ` : ""}${unchecked.length === 1 ? "one reason" : `${unchecked.length} reasons`} could not be checked`;
  }
  return `${repo} · ${d.reasons.length === 1 ? "its one reason holds" : `all ${d.reasons.length} reasons hold`}`;
}

function Trailing({ d }: { d: RealWorldDecision }) {
  const extraGate = IMPLIED[d.verdict] !== d.gate;
  return (
    <span className={s.trail}>
      {extraGate && <GateBadge gate={d.gate} title={`Agent gate: ${d.gate.toLowerCase()}`} />}
      <VerdictBadge verdict={d.verdict} />
    </span>
  );
}

const EXT = <span aria-hidden="true"> ↗</span>;

function Detail({ d, id }: { d: RealWorldDecision; id: string }) {
  return (
    <div id={id} className={s.detail}>
      <p className="t-footnote">
        Record <span className="id">{d.id}</span> · {d.repo} · <time dateTime={d.date}>{longDate(d.date)}</time> · status {d.status}
      </p>
      <blockquote className={s.quote}>“{d.quote}”</blockquote>

      {d.retired && (
        <p className={s.retired}>
          <span className="lead-in">Retired on {longDate(d.retired.date)}.</span>{" "}
          <a href={d.retired.url} target="_blank" rel="noopener" className="link">{d.retired.title}{EXT}</a>
          {d.retired.quote && <> “{d.retired.quote}”</>}
          {d.retired.commit && <> · <a href={d.retired.commit} target="_blank" rel="noopener" className="link">Commit{EXT}</a></>}
        </p>
      )}

      {d.reasons.length > 0 && (
        <>
          <h4 className={s.reasonsHead}>The reasons nobody wrote down</h4>
          <ul className={s.reasons}>
            {d.reasons.map(r => {
              const ev = decidingEvent(r.evidence);
              return (
                <li key={r.id} className={s.reason}>
                  <span className={s.reasonMain}>
                    <span className={s.reasonText}>{r.text}</span>
                    <span className={cx(s.reasonEv, ev?.rel === "CONTRADICTS" && s.contra)}>
                      {ev ? <>{ev.rel === "CONTRADICTS" ? "Contradicted by" : "Supported by"} {prettyDates(ev.title)} · checked {longDate(ev.at)}</>
                        : r.unchecked ? <>Could not be checked: {prettyDates(r.unchecked)}</>
                        : <>No evidence either way.</>}
                    </span>
                  </span>
                  <StateTag state={r.state} />
                </li>
              );
            })}
          </ul>
        </>
      )}

      <a href={d.url} target="_blank" rel="noopener" className={cx("link", s.out)}>Read the record on GitHub{EXT}</a>
    </div>
  );
}

function Item({ d, compact }: { d: RealWorldDecision; compact: boolean }) {
  const [open, setOpen] = useState(false);
  const detailId = useId();
  const main = (
    <span className={s.main}>
      <span className={cx(s.title, compact && s.clip)}>{d.title}</span>
      <span className={cx(s.sub, compact && s.clip)}>{why(d)}</span>
    </span>
  );
  if (compact) {
    return (
      <li className={s.item}>
        <a className={s.row} href={d.url} target="_blank" rel="noopener" aria-label={`${d.title}, ${d.verdict.toLowerCase()}. Opens the record on GitHub.`}>
          {main}<Trailing d={d} /><span className={s.chev} aria-hidden="true">›</span>
        </a>
      </li>
    );
  }
  return (
    <li className={cx(s.item, open && s.open)}>
      <button type="button" className={s.row} aria-expanded={open} aria-controls={detailId} onClick={() => setOpen(o => !o)}>
        {main}<Trailing d={d} /><span className={cx(s.chev, s.turn)} aria-hidden="true">›</span>
      </button>
      {open && <Detail d={d} id={detailId} />}
    </li>
  );
}

/** `after` renders as a last row inside the same group (e.g. the "See all" link on the landing page). */
export default function RealWorldIndex({ data, limit, compact, header, after }:
  { data: RealWorldResponse; limit?: number; compact?: boolean; header?: ReactNode; after?: ReactNode }) {
  const rows = sortRecords(data.decisions).slice(0, limit ?? undefined);
  return (
    <Group header={header} label="Public decision records">
      {rows.length ? (
        <ul className={s.list}>
          {rows.map(d => <Item key={d.id} d={d} compact={!!compact} />)}
        </ul>
      ) : <p className={s.none}>No records match.</p>}
      {after && <div className={s.after}>{after}</div>}
    </Group>
  );
}
