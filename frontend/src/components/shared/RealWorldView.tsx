"use client";
// /app/realworld/: the 25 public ADRs. A large title, one sentence, a stat row, a filter and the grouped list;
// tap a record to see every unwritten reason, its state and the check that decided it.
import { useMemo, useState } from "react";
import type { RealWorldResponse, Verdict } from "@/lib/types";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Segmented } from "@/components/ui";
import EmptyState from "@/components/ui/EmptyState";
import { longDate } from "@/lib/format";
import RealWorldIndex from "./RealWorldIndex";
import RealWorldDocket from "./RealWorldDocket";
import s from "./RealWorldView.module.css";

type Filter = "all" | "MOOT" | "RETIRED" | "HOLDS";
const FILTERS: [Filter, string][] = [["all", "All"], ["MOOT", "Moot"], ["RETIRED", "Retired"], ["HOLDS", "Holds"]];
const GROUP_WORD: Record<Filter, string> = { all: "All records", MOOT: "Moot", RETIRED: "Retired", HOLDS: "Holds" };

function Loaded({ data }: { data: RealWorldResponse }) {
  const [filter, setFilter] = useState<Filter>("all");
  const shown = useMemo<RealWorldResponse>(() => ({
    ...data, decisions: filter === "all" ? data.decisions : data.decisions.filter(d => d.verdict === (filter as Verdict)),
  }), [data, filter]);
  const titles = useMemo(() => Object.fromEntries(data.decisions.map(d => [d.id, d.title])), [data]);

  return (
    <>
      <RealWorldDocket summary={data.summary} className={s.docket} />
      <div className={s.filter}>
        <Segmented label="Show records" value={filter} options={FILTERS} onChange={setFilter} />
      </div>
      <div aria-live="polite">
        <RealWorldIndex data={shown} header={<span>{GROUP_WORD[filter]} · {shown.decisions.length}</span>} />
      </div>
      {data.shared.length > 0 && (
        <div className={s.notes}>
          {data.shared.map(x => (
            <p key={x.tool} className="t-footnote">
              <span className="lead-in">{x.tool} is a reason behind {x.records.length} records</span>{" "}
              ({x.records.map((id, i) => <span key={id}>{i ? ", " : ""}<span className="id" title={titles[id]}>{id}</span></span>)}); one check answers for {x.records.length === 2 ? "both" : "all of them"}.
            </p>
          ))}
        </div>
      )}
    </>
  );
}

export default function RealWorldView() {
  const { data, error, loading, reload } = useApi(() => api.realworld(), []);
  return (
    <div className={s.page}>
      <header className={s.head}>
        <h1 className="t-large">Real world</h1>
        <p className="t-callout muted">
          <span className="lead-in">
            {data ? `${data.summary.records} public decision records, checked on ${longDate(data.summary.checked_on)}.` : "Public decision records, checked."}
          </span>{" "}
          Each tool choice rests on reasons nobody wrote down: the tool is still maintained, still open source and has no known
          vulnerability. Moot checks each one against GitHub and OSV.dev and gives the verdict from the same path queries as the ledger.
        </p>
        <p className="t-footnote">These dates are fixed by the check, not by the as-of control.</p>
      </header>
      {loading && !data && (
        <div className={s.skel} aria-busy="true" aria-label="Loading the public records">
          {Array.from({ length: 8 }, (_, i) => <div key={i} className="skeleton" style={{ height: 44 }} />)}
        </div>
      )}
      {error && <EmptyState kind="error" title="The public records could not be loaded." detail={error}
        action={<button type="button" className="btn ghost small" onClick={reload}>Try again</button>} />}
      {data && <Loaded data={data} />}
    </div>
  );
}
