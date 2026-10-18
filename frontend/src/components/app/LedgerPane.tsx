"use client";
// Left column of the ledger (/app/ledger/): large title, the verdict summary (tap to filter; ?v=MOOT opens filtered), and
// the ledger as grouped lists per verdict for the current as-of and depth. The full rot chart opens in a sheet. Questions
// are asked on Ask (/app/), not here.
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAppState } from "@/lib/appState";
import { longDate } from "@/lib/format";
import { Sheet, VERDICT_WORD, cx } from "@/components/ui";
import EmptyState from "@/components/ui/EmptyState";
import { VERDICT_ORDER } from "@/lib/format";
import type { Verdict } from "@/lib/types";
import LedgerDocket from "./LedgerDocket";
import LedgerRows, { LedgerSkeleton } from "./LedgerRows";
import RotChart from "./RotChart";
import ShellPortal from "./ShellPortal";
import s from "./ledger.module.css";

const tenantName = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

export default function LedgerPane() {
  const { asOf, depth, selected, select, setAsOf } = useAppState();
  const v = useSearchParams().get("v") as Verdict | null;
  const ledger = useApi(() => api.ledger({ as_of: asOf, depth }), [asOf, depth]);
  const timeline = useApi(() => api.timeline(depth), [depth]);
  const health = useApi(() => api.health(), []);
  const [verdict, setVerdict] = useState<Verdict | null>(v && VERDICT_ORDER.includes(v) ? v : null);
  const [q, setQ] = useState("");
  const [filterOpen, setFilterOpen] = useState(false);
  const [trend, setTrend] = useState(false);
  const filterRef = useRef<HTMLInputElement>(null);
  const fid = useId();

  useEffect(() => { if (filterOpen) filterRef.current?.focus(); }, [filterOpen]);

  const all = useMemo(() => ledger.data?.decisions ?? [], [ledger.data]);
  const rows = useMemo(() => {
    const f = q.trim().toLowerCase();
    return all.filter(d => (!verdict || d.verdict === verdict) &&
      (!f || `${d.id} ${d.title} ${d.owner ?? ""} ${d.systems.join(" ")}`.toLowerCase().includes(f)));
  }, [all, q, verdict]);

  const open = (id: string) => select(id);
  const filtered = !!verdict || q.trim() !== "";
  const clear = () => { setQ(""); setVerdict(null); setFilterOpen(false); };

  return (
    <div className={s.pane}>
      <header className={s.head}>
        <h1 className={cx("t-large", s.title)}>Ledger</h1>
        <p className={cx("t-footnote", s.sub)}>
          {health.data ? `${tenantName(health.data.tenant)} · ` : ""}
          {ledger.data ? `as of ${longDate(ledger.data.as_of)}` : asOf ? `as of ${longDate(asOf)}` : "today"} · depth {depth}
          {asOf && <> · <button type="button" className={s.inlineBtn} onClick={() => setAsOf(null)}>Back to today</button></>}
        </p>
      </header>


      <LedgerDocket ledger={ledger.data} points={timeline.data?.points ?? null} asOf={asOf}
        verdict={verdict} onVerdict={setVerdict} onTrend={() => setTrend(true)}
        onFilter={filterOpen ? undefined : () => setFilterOpen(true)} />

      <ShellPortal>
        <Sheet open={trend} title="Moot over time" onClose={() => setTrend(false)} cancelLabel="Done">
          <RotChart />
        </Sheet>
      </ShellPortal>

      {filtered && ledger.data && (
        <div className={s.listBar}>
          <span className="t-footnote" aria-live="polite">
            Showing {rows.length} of {all.length}{verdict ? <> · {VERDICT_WORD[verdict].toLowerCase()} only</> : null}
          </span>
          <button type="button" className={s.inlineBtn} onClick={clear}>Clear</button>
        </div>
      )}
      {filterOpen && (
        <div className={s.filterRow}>
          <label htmlFor={fid} className="sr-only">Filter the ledger by title, owner or system</label>
          <input id={fid} ref={filterRef} type="search" className={cx("input", s.filter)} value={q} onChange={e => setQ(e.target.value)}
            onKeyDown={e => { if (e.key === "Escape") { setQ(""); setFilterOpen(false); } }}
            placeholder="Title, owner or system" autoComplete="off" spellCheck={false} />
          <button type="button" className={cx("btn", "plain", s.filterDone)} onClick={() => { setQ(""); setFilterOpen(false); }}>Cancel</button>
        </div>
      )}

      {ledger.error && !ledger.data ? (
        <EmptyState kind="error" title="The ledger could not load." detail={ledger.error} />
      ) : !ledger.data ? (
        <LedgerSkeleton />
      ) : (
        <div className={cx(ledger.loading && s.busy)} aria-busy={ledger.loading}>
          {ledger.error && <p className="t-footnote">Could not refresh. {ledger.error}</p>}
          {rows.length ? <LedgerRows rows={rows} selected={selected} onOpen={open} />
            : <p className={cx("t-footnote", s.none)}>Nothing matches as of {longDate(ledger.data.as_of)}. <button type="button" className={s.inlineBtn} onClick={clear}>Show all</button></p>}
        </div>
      )}
    </div>
  );
}
