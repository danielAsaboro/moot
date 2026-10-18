"use client";
// The agent gate page (/app/gate/): every standing decision grouped by what an agent may do with it today.
import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAppState } from "@/lib/appState";
import { longDate } from "@/lib/format";
import { GATE_WORD, Group, Segmented, StatCard } from "@/components/ui";
import EmptyState from "@/components/ui/EmptyState";
import type { GateDecision } from "@/lib/types";
import AskPanel from "./AskPanel";
import GateCard from "./GateCard";
import { OUTCOMES, byVerdictThenId, itemFromLedger, itemFromPublic, useGateRun, type GateItem, type Source } from "./gateData";
import s from "./GateBoard.module.css";

const NOTE: Record<GateDecision, string> = {
  DENY: "Do not act on these.",
  REVALIDATE: "Check with the owner first.",
  ALLOW: "Safe to act on.",
};
const TONE = { DENY: "moot", REVALIDATE: "disputed", ALLOW: "holds" } as const;

function SkeletonList() {
  return (
    <div className={s.groups} aria-hidden="true">
      {[0, 1].map(g => (
        <div key={g} className={s.skelGroup}>
          <div className="skeleton" style={{ width: 90, marginLeft: 16 }} />
          <div className={s.skelBody}>
            {[0, 1, 2].map(i => (
              <div key={i} className={s.skelRow}>
                <div className="skeleton" style={{ width: "55%" }} />
                <div className="skeleton" style={{ width: "80%", marginTop: 8 }} />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function GateBoard() {
  const { asOf, link } = useAppState();
  const [source, setSource] = useState<Source>("larkspur");
  const [only, setOnly] = useState<GateDecision | null>(null);

  const ledger = useApi(() => api.ledger({ as_of: asOf }), [asOf]);
  const rows = source === "larkspur" ? ledger.data?.decisions ?? null : null;
  const run = useGateRun(rows, ledger.data?.as_of ?? asOf);
  const rw = useApi(() => (source === "public" ? api.realworld() : Promise.resolve(null)), [source]);
  const checkedOn = rw.data?.summary.checked_on ?? null;

  const items: GateItem[] = useMemo(() => {
    if (source === "larkspur") {
      return (ledger.data?.decisions ?? []).flatMap(r => {
        const g = run.gates[r.id];
        return g ? [itemFromLedger(r, g, link("/app/", { d: r.id }))] : [];
      });
    }
    return rw.data ? rw.data.decisions.map(itemFromPublic) : [];
  }, [source, ledger.data, run.gates, rw.data, link]);

  const count = (g: GateDecision) => items.filter(i => i.gate === g).length;
  const loading = source === "larkspur" ? ledger.loading : rw.loading;
  const error = source === "larkspur" ? ledger.error : rw.error;
  const reload = source === "larkspur" ? ledger.reload : rw.reload;
  const expected = source === "larkspur" ? ledger.data?.decisions.length ?? 0 : rw.data?.decisions.length ?? 0;
  const checked = source === "larkspur" ? Object.keys(run.gates).length : items.length;
  const failedIds = source === "larkspur" ? Object.keys(run.failed) : [];
  const checking = source === "larkspur" && checked + failedIds.length < expected;

  const sample = source === "larkspur" ? Object.values(run.gates)[0] : null;
  const shownAsOf = source === "larkspur" ? ledger.data?.as_of ?? null : checkedOn;
  const callId = source === "larkspur"
    ? (ledger.data?.decisions.map(r => r.id).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))[0] ?? null)
    : rw.data?.decisions[0]?.id ?? null;
  const call = callId && shownAsOf
    ? `GET /api/gate/${callId}?as_of=${shownAsOf}${source === "public" ? "&graph=public_adrs" : ""}`
    : null;

  const pick = (k: Source) => { setSource(k); setOnly(null); };
  const shown = only ? [only] : OUTCOMES;

  return (
    <div className={s.page}>
      <header className={s.head}>
        <h1 className={`t-large ${s.h1}`}>Agent gate</h1>
        <p className={s.lede}>
          <span className="lead-in">An agent asks before it acts on a rule.</span>{" "}
          The graph answers Allow, Deny or Revalidate, with the path.
        </p>
        <div className={s.switch}>
          <Segmented<Source> label="Which decisions" value={source} onChange={pick}
            options={[["larkspur", "Larkspur"], ["public", "Public records"]]} />
        </div>
      </header>

      {error ? (
        <EmptyState kind="error" title="The gate could not load." detail={error}
          action={<button type="button" className="btn ghost small" onClick={reload}>Try again</button>} />
      ) : loading ? (
        <>
          <span className="sr-only" role="status">{source === "larkspur" ? "Reading the ledger…" : "Reading the public records…"}</span>
          <div className={s.stats} aria-hidden="true">{OUTCOMES.map(o => <div key={o} className={`skeleton ${s.skelStat}`} />)}</div>
          <SkeletonList />
        </>
      ) : expected === 0 ? (
        <EmptyState kind="empty" title="No decisions in this graph yet." />
      ) : (
        <>
          <div className={s.stats} role="group" aria-label="Filter by answer">
            {OUTCOMES.map(o => (
              <StatCard key={o} label={GATE_WORD[o]} value={count(o)} tone={TONE[o]} foot={NOTE[o]} on={only === o}
                onClick={() => setOnly(v => (v === o ? null : o))}
                ariaLabel={`${GATE_WORD[o]}: ${count(o)}. ${only === o ? "Show all answers" : `Show only ${GATE_WORD[o]}`}`} />
            ))}
          </div>

          <p className={`t-footnote ${s.status}`} role="status" aria-live="polite">
            {checking
              ? `Checked ${checked} of ${expected}`
              : source === "larkspur"
                ? `${checked === expected ? `All ${expected}` : `${checked} of ${expected}`} checked as of ${longDate(shownAsOf)}${sample ? `, up to ${sample.depth} hops deep` : ""}.`
                : `${expected} public records, checked against GitHub and OSV on ${longDate(checkedOn)}.`}
            {only && (
              <> {" "}<button type="button" className={`btn plain ${s.clear}`} onClick={() => setOnly(null)}>Show all</button></>
            )}
          </p>

          {failedIds.length > 0 && !checking && (
            <p className={`t-footnote ${s.status}`} role="status">
              {failedIds.length === 1 ? "One check" : `${failedIds.length} checks`} did not come back (
              {failedIds.map((id, i) => <span key={id}>{i ? ", " : ""}<span className="id">{id}</span></span>)}).{" "}
              <button type="button" className={`btn plain ${s.clear}`} onClick={run.retry}>Retry</button>
            </p>
          )}

          <div className={s.groups}>
            {shown.map(o => {
              const list = items.filter(i => i.gate === o).sort(byVerdictThenId);
              if (!list.length && !only) return null;
              return (
                <Group key={o} label={`${GATE_WORD[o]}, ${list.length}`} header={<span>{GATE_WORD[o]} · {list.length}</span>}>
                  {list.length
                    ? list.map(i => <GateCard key={i.id} item={i} />)
                    : <p className={`t-sub ${s.none}`}>{checking ? "Checking…" : "None."}</p>}
                </Group>
              );
            })}
          </div>
        </>
      )}

      <AskPanel call={call} />
    </div>
  );
}
