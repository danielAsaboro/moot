"use client";
// Landing section 6, keynote numbers on paper. Every number is read from /api/evals (the committed eval results).
import { api, type EvalsResponse } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Card } from "@/components/ui";
import EmptyState from "@/components/ui/EmptyState";
import { longDate } from "@/lib/format";
import { DitherField } from "./ProofDither";
import s from "./Proof.module.css";

const RESULTS = "https://github.com/danielAsaboro/moot/blob/main/eval/";
const fmtRecall = (r: number) => r.toFixed(2);

function Stat({ value, unit, children }: { value: string; unit: string; children: React.ReactNode }) {
  return (
    <Card className={s.card}>
      <p className={s.cardValue}><span className="tabular">{value}</span> <span className={s.cardUnit}>{unit}</span></p>
      <p className={s.cardText}>{children}</p>
    </Card>
  );
}

function Result({ data }: { data: EvalsResponse }) {
  const gate = data.gate;
  const r = data.retrieval;
  const m = gate?.methods ?? {};
  const moot = m.moot;
  const nBlock = Number(gate?.n_block ?? 0);
  const nHold = Number(gate?.n_hold ?? 0);
  const n = Number(gate?.n ?? nBlock + nHold);
  const perDecision = (gate?.moot ?? {}) as Record<string, { gate?: string; reasons?: string[] }>;
  const blocks = moot?.false_blocks ?? [];
  const neverDenied = blocks.length > 0 && blocks.every(id => perDecision[id]?.gate === "REVALIDATE");
  const allUnevidenced = blocks.length > 0 && blocks.every(id => perDecision[id]?.reasons?.includes("premise_unevidenced"));

  return (
    <>
      {moot && (
        <>
          <div className={s.keynote}>
            <DitherField level={2} />
            <p className={s.giant} aria-label={`${moot.false_allows.length} of ${nBlock}`}>
              <span className="tabular">{moot.false_allows.length}</span> <span className={s.of}>of {nBlock}</span>
            </p>
          </div>
          <p className={s.caption}>dead decisions an agent was allowed to act on, with the Moot gate in front of it.</p>
        </>
      )}

      <div className={s.grid}>
        {m.adr && (
          <Stat value={`${m.adr.false_allows.length}`} unit={`of ${nBlock}`}>
            allowed when the agent trusts the decision record and stops there.
          </Stat>
        )}
        {m.bm25 && (
          <Stat value={`${m.bm25.false_allows.length}`} unit={`of ${nBlock}`}>
            allowed by keyword search over the documents, with change cues.
          </Stat>
        )}
        {r && (
          <Stat value={fmtRecall(r.graph_recall)} unit={`vs ${fmtRecall(r.bm25_recall)}`}>
            recall of the document that kills a reason: graph path vs keyword search.
          </Stat>
        )}
      </div>

      <div className={s.notes}>
        {gate && (
          <p className="t-footnote">
            <span className="lead-in">Method.</span> {n} Larkspur decisions as of {longDate(gate.as_of)}: {nBlock} should be
            stopped, {nHold} hold. The Moot gate checks each at depth 6; the baselines use no model.
            {blocks.length > 0 && (
              <> The cost: it sent {blocks.length} of the {nHold} decisions that hold back to revalidate
                {neverDenied ? ", never denied" : ""}{allUnevidenced ? ", because a reason has no dated evidence either way" : ""}.</>
            )}
          </p>
        )}
        {r && (
          <p className="t-footnote">
            Recall is measured on {r.n} moot or disputed decisions and {r.docs.toLocaleString("en-US")} documents, top {r.k}.
            The graph&apos;s {fmtRecall(r.graph_recall)} is a consistency check, not a search result: its edges and the answer
            key come from the same spec.
          </p>
        )}
        <p className="t-footnote">
          Larkspur is a synthetic company built for these evals. Method and data:{" "}
          <a className="link" href={`${RESULTS}results_gate.md`} target="_blank" rel="noopener">eval/results_gate.md</a> and{" "}
          <a className="link" href={`${RESULTS}results.md`} target="_blank" rel="noopener">eval/results.md</a>.
        </p>
      </div>
    </>
  );
}

export default function Proof() {
  const { data, error, loading } = useApi(() => api.evals(), []);
  return (
    <section id="proof" className={s.section} aria-labelledby="proof-title">
      <div className={`wrap ${s.inner}`}>
        <h2 id="proof-title" className="t-eyebrow">Proof</h2>
        {loading && (
          <div className={s.loading} aria-busy="true" aria-label="Loading the eval results">
            <div className="skeleton" style={{ width: 280, height: 150 }} />
            <div className="skeleton" style={{ width: "min(560px, 100%)", height: 24 }} />
            <div className={s.grid}>{[0, 1, 2].map(i => <div key={i} className="skeleton" style={{ height: 132, borderRadius: "var(--r-card)" }} />)}</div>
          </div>
        )}
        {error && <div className={s.state}><EmptyState kind="error" title="The eval results could not be loaded." detail={error} /></div>}
        {data && <Result data={data} />}
      </div>
    </section>
  );
}
