"use client";
// The ledger summary: three stat cards (Moot with a tiny rot sparkline, Disputed, Holds), each a filter toggle,
// then one quiet line for Undocumented and Retired (also toggles) and the "Show trend" button.
import { useMemo } from "react";
import { StatCard, cx } from "@/components/ui";
import type { LedgerResponse, TimelinePoint, Verdict } from "@/lib/types";
import { RotSpark } from "./RotChart";
import s from "./ledger.module.css";

export default function LedgerDocket({ ledger, points, asOf, verdict, onVerdict, onTrend, onFilter }: {
  ledger: LedgerResponse | null;
  points: TimelinePoint[] | null;
  asOf: string | null;
  verdict: Verdict | null;
  onVerdict: (v: Verdict | null) => void;
  onTrend: () => void;
  /** Shows the quiet text filter; omitted while it is already open. */
  onFilter?: () => void;
}) {
  const counts = useMemo(() => {
    const c: Partial<Record<Verdict, number>> = {};
    for (const d of ledger?.decisions ?? []) c[d.verdict] = (c[d.verdict] ?? 0) + 1;
    return c;
  }, [ledger]);
  const n = (v: Verdict) => counts[v] ?? 0;
  const toggle = (v: Verdict) => onVerdict(verdict === v ? null : v);
  const value = (v: Verdict) => ledger ? n(v) : <span className={cx("skeleton", s.skCount)} aria-hidden />;
  const aria = (v: Verdict, word: string) => `${ledger ? n(v) : "…"} ${word}. ${verdict === v ? "Showing only these; press to show all" : "Show only these"}`;

  return (
    <div className={s.summary}>
      <div className={s.stats} role="group" aria-label="Filter by verdict">
        <StatCard label="Moot" tone="moot" value={value("MOOT")} on={verdict === "MOOT"} onClick={() => toggle("MOOT")}
          ariaLabel={aria("MOOT", "moot")}
          foot={points && points.length ? <RotSpark points={points} asOf={asOf} /> : <span className={s.sparkSpace} />} />
        <StatCard label="Disputed" tone="disputed" value={value("DISPUTED")} on={verdict === "DISPUTED"} onClick={() => toggle("DISPUTED")}
          ariaLabel={aria("DISPUTED", "disputed")} foot={<span className={s.cardFoot}>needs a ruling</span>} />
        <StatCard label="Holds" tone="holds" value={value("HOLDS")} on={verdict === "HOLDS"} onClick={() => toggle("HOLDS")}
          ariaLabel={aria("HOLDS", "hold")} foot={<span className={s.cardFoot}>still valid</span>} />
      </div>
      <div className={s.quiet}>
        <span className="t-footnote">
          {(["UNDOCUMENTED", "RETIRED"] as Verdict[]).map((v, i) => (
            <span key={v}>
              {i > 0 && <span aria-hidden="true"> · </span>}
              <button type="button" className={cx(s.textToggle, verdict === v && s.textOn)} aria-pressed={verdict === v}
                onClick={() => toggle(v)} disabled={!ledger}>
                {ledger ? n(v) : "–"} {v === "UNDOCUMENTED" ? "undocumented" : "retired"}
              </button>
            </span>
          ))}
        </span>
        <span className={s.quietActions}>
          {onFilter && <button type="button" className={cx("btn", "plain", s.trendBtn)} onClick={onFilter}>Filter</button>}
          <button type="button" className={cx("btn", "plain", s.trendBtn)} onClick={onTrend} aria-haspopup="dialog">Show trend</button>
        </span>
      </div>
    </div>
  );
}
