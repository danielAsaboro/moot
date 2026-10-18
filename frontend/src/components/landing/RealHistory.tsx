"use client";
// Landing: what Moot said on real repositories' own history, before their maintainers acted, and the held-out score graded
// by those repositories. Every number is read from /api/evals (eval/results_backtest.json, eval/results_heldout.json).
import { api, type EvalsResponse } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Card } from "@/components/ui";
import { longDate } from "@/lib/format";
import { DitherField } from "./ProofDither";
import s from "./Proof.module.css";

const RESULTS = "https://github.com/danielAsaboro/moot/blob/main/eval/";

interface Caught { title: string; repo: string; url: string; denied_from: string; abandoned: string; lead_days: number; why: string }
interface Backtest { tool_decisions: number; tool_deaths: number; repos: number; caught: Caught[]; median_lead_days: number | null;
  methods: Record<string, { caught: number; flagged: number; dead: number }>; flag_reading: Record<string, number> }
interface ArmScore { right: number; n: number; caught: number; dead: number; flagged: number }
interface Heldout { t0: string; results: { test: Record<string, ArmScore> } }

const n = (x: number) => x.toLocaleString("en-US");

function Body({ data }: { data: EvalsResponse }) {
  const bt = data.backtest as Backtest | undefined;
  const ho = data.heldout as Heldout | undefined;
  if (!bt) return null;
  const longest = [...bt.caught].sort((a, b) => b.lead_days - a.lead_days)[0];
  const others = bt.caught.filter(c => c !== longest);
  const moot = bt.methods["Moot gate (DENY)"];
  const age = bt.methods["age ≥ 3 years"];
  const real = bt.flag_reading?.real ?? 0;
  const t = ho?.results.test;
  return (
    <>
      {longest && (
        <>
          <div className={s.keynote}>
            <DitherField level={2} />
            <p className={s.giant} aria-label={`${longest.lead_days} days`}>
              <span className="tabular">{n(longest.lead_days)}</span> <span className={s.of}>days early</span>
            </p>
          </div>
          <p className={s.caption}>
            Moot denied <a className="link" href={longest.url} target="_blank" rel="noopener">{longest.title.replace(/^\d+\.\s*/, "")}</a> on{" "}
            {longDate(longest.denied_from)}. {longest.repo} deprecated it on {longDate(longest.abandoned)}.
          </p>
        </>
      )}
      <div className={s.grid}>
        {others.map(c => (
          <Card key={c.url} className={s.card}>
            <p className={s.cardValue}><span className="tabular">{n(c.lead_days)}</span> <span className={s.cardUnit}>days</span></p>
            <p className={s.cardText}>before {c.repo} dropped “{c.title.replace(/^\d+\.\s*/, "")}”, Moot said DENY: {c.why.split(" was ")[0]} was no longer true.</p>
          </Card>
        ))}
        {bt.median_lead_days !== null && (
          <Card className={s.card}>
            <p className={s.cardValue}><span className="tabular">{n(Math.round(bt.median_lead_days))}</span> <span className={s.cardUnit}>days</span></p>
            <p className={s.cardText}>median lead on the {moot.caught} deaths it caught, of {moot.dead} that outside evidence could see.</p>
          </Card>
        )}
        <Card className={s.card}>
          <p className={s.cardValue}><span className="tabular">{real}</span> <span className={s.cardUnit}>of {moot.flagged}</span></p>
          <p className={s.cardText}>flags on ADRs still marked accepted whose reason really died upstream; the age rule raises {age.flagged} flags and names no reason.</p>
        </Card>
      </div>
      <div className={s.notes}>
        <p className="t-footnote">
          <span className="lead-in">Method.</span> {bt.repos} public repositories rewound month by month; Moot saw only the evidence that existed each
          month, and the answer key is what the maintainers later committed. It caught {moot.caught} of {moot.dead} tool deaths, the age rule {age.caught}:
          too few to rank anything on recall, and the file says so.
          {t && (
            <> On the held-out test graded by the repositories themselves (cut on {longDate(ho!.t0)}), Moot was right on {t.moot.right} of {t.moot.n};
              calling everything HOLDS was right on {t.majority.right}.</>
          )}{" "}
          <a className="link" href={`${RESULTS}results_backtest.md`} target="_blank" rel="noopener">eval/results_backtest.md</a>
          {t && <> · <a className="link" href={`${RESULTS}results_heldout.md`} target="_blank" rel="noopener">eval/results_heldout.md</a></>}
        </p>
      </div>
    </>
  );
}

export default function RealHistory() {
  const { data } = useApi(() => api.evals(), []);
  return (
    <section id="history" className={s.section} aria-labelledby="history-title">
      <div className={`wrap ${s.inner}`}>
        <h2 id="history-title" className="t-eyebrow">On real history</h2>
        {data && <Body data={data} />}
      </div>
    </section>
  );
}
