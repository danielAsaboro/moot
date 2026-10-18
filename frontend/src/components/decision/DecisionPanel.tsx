"use client";
// The selected decision, calm: id and system, title, one solid verdict pill, one sentence that says why, one grey line.
// Then the hero (the isometric drawing of the rows), a segmented control over four views of the same audit
// (Summary, Graph, Steps, Queries), the gate in a sheet and the decision record in a sheet.
// Everything on it comes from GET /api/decision/{id}.
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAppState } from "@/lib/appState";
import type { DecisionResponse } from "@/lib/types";
import { VerdictBadge, cx } from "@/components/ui";
import EmptyState from "@/components/ui/EmptyState";
import AuditTab from "./AuditTab";
import AuditSteps from "./AuditSteps";
import CypherSpec from "./CypherSpec";
import IsoGraph from "@/components/graph/IsoGraph";
import { VerdictMeta, VerdictWhy } from "./VerdictStamp";
import { GateSheet } from "./GateBlock";
import PanelAdr from "./PanelAdr";
import PanelTabs, { paneId, tabLabel, type PanelTab } from "./PanelTabs";
import s from "./Panel.module.css";

// The chosen view outlives the panel, so switching decisions keeps the reader on the same view.
let rememberedTab: PanelTab = "audit";

/** True on phone widths, where the drawing is shorter. */
function useNarrow(query = "(max-width: 640px)") {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const m = matchMedia(query);
    const on = () => setNarrow(m.matches);
    on(); m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, [query]);
  return narrow;
}

export default function DecisionPanel({ id }: { id: string }) {
  const { asOf, depth, select } = useAppState();
  const status = useRef(0);
  const { data, error, loading, reload } = useApi<DecisionResponse>(() => {
    status.current = 0;
    return api.decision(id, { as_of: asOf, depth }).catch((e: unknown) => {
      if (e instanceof ApiError) status.current = e.status;
      throw e;
    });
  }, [id, asOf, depth]);
  const [tab, setTabState] = useState<PanelTab>(rememberedTab);
  const setTab = (t: PanelTab) => { rememberedTab = t; setTabState(t); };
  const [gateOpen, setGateOpen] = useState(false);
  const closeGate = useCallback(() => setGateOpen(false), []);
  const paneRef = useRef<HTMLDivElement>(null);
  const narrow = useNarrow();
  const prefix = useId().replace(/:/g, "");

  if (error) {
    return (
      <div className={s.panel}>
        {status.current === 404
          ? <EmptyState kind="not_in_graph" title={`${id} is not in the graph`} detail="Moot only audits decisions it has a record of. Pick one from the ledger." />
          : <EmptyState kind="error" title="This decision could not be loaded." detail={error}
              action={<button type="button" className="btn ghost small" onClick={reload}>Try again</button>} />}
      </div>
    );
  }
  // Keep the last panel on screen while a new depth or date loads; skeleton only on first load or a new id.
  if (!data || (loading && data.audit.decision.id !== id)) return <PanelSkeleton />;

  const a = data.audit;
  const d = a.decision;
  const notYet = a.verdict === "NOT_YET";
  const showGate = !notYet && a.verdict !== "RETIRED" && !!data.gate;

  const explore = () => {
    setTab("graph");
    const smooth = !matchMedia("(prefers-reduced-motion: reduce)").matches;
    requestAnimationFrame(() => paneRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" }));
  };

  return (
    <article className={cx(s.panel, loading && s.stale)} aria-busy={loading} aria-labelledby={`${prefix}-title`}>
      <header className={s.head}>
        <p className="t-footnote" style={{ margin: 0 }}>
          <span className="id">{d.id}</span>{a.systems.length > 0 && <> · {a.systems.join(", ")}</>}
        </p>
        <div className={s.titleRow}>
          <h2 id={`${prefix}-title`} className={cx("t-large", s.title)}>{d.title}</h2>
          <VerdictBadge verdict={a.verdict} fill size="md" className={s.pill} />
        </div>
        <VerdictWhy audit={a} onSelect={select} />
        {!notYet && <VerdictMeta audit={a} />}
      </header>

      {/* One drawing per screen: the preview is the hero everywhere except the Graph tab, which shows the full one. */}
      {!notYet && tab !== "graph" && (
        <figure className={s.hero}>
          <div className={s.frame}>
            <IsoGraph audit={a} gate={data.gate} variant="preview" height={narrow ? 200 : 300} onExpand={explore} />
          </div>
          <figcaption className={cx("t-footnote", s.caption)}>
            <span>Drawn from the rows FalkorDB returned for this answer.</span>
            <button type="button" className={s.more} onClick={explore}>Explore in 3D ›</button>
          </figcaption>
        </figure>
      )}

      {!notYet && (
        <div className={s.views}>
          <div className={s.toolbar}>
            <PanelTabs value={tab} onChange={setTab} prefix={prefix} />
          </div>
          <div ref={paneRef} role="tabpanel" id={paneId(prefix, tab)} aria-label={tabLabel(tab)} className={s.pane} tabIndex={-1}>
            {tab === "audit" && <AuditTab data={data} onChanged={reload} onGateDetails={showGate ? () => setGateOpen(true) : undefined} />}
            {tab === "graph" && <IsoGraph audit={a} gate={data.gate} />}
            {tab === "steps" && <AuditSteps audit={a} />}
            {tab === "cypher" && <CypherSpec queries={data.queries} />}
          </div>
        </div>
      )}

      <footer className={s.foot}>
        <PanelAdr key={d.id} id={d.id} source={d.source} />
      </footer>

      {showGate && <GateSheet gate={data.gate} asOf={asOf} open={gateOpen} onClose={closeGate} />}
    </article>
  );
}

function PanelSkeleton() {
  return (
    <div className={s.panel} aria-busy="true" aria-label="Loading decision">
      <div className={s.head}>
        <div className="skeleton" style={{ width: 120 }} />
        <div className="skeleton" style={{ width: "62%", height: 36 }} />
        <div className="skeleton" style={{ width: 72, height: 26, borderRadius: "var(--r-pill)" }} />
        <div className="skeleton" style={{ width: "92%", height: 20 }} />
        <div className="skeleton" style={{ width: "70%" }} />
      </div>
      <div className={cx("skeleton", s.skelHero)} />
      <div className="skeleton" style={{ width: 300, maxWidth: "100%", height: 30 }} />
    </div>
  );
}
