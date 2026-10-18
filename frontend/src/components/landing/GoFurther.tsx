"use client";
// Landing: past the demo company. One quiet grouped list into the features that read real data or people: the graphs
// /api/graphs lists (the backtest and each ingested GitHub repository) and the People view. Counts come from the API.
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Group, Row, SectionHead } from "@/components/ui";
import s from "./RealWorldPreview.module.css";

export default function GoFurther() {
  const { data } = useApi(() => api.graphs(), []);
  const repos = (data?.graphs ?? []).filter(g => g.kind === "github");
  const backtest = data?.graphs.find(g => g.kind === "backtest");
  return (
    <section id="further" className={s.section} aria-label="Go further">
      <div className="wrap">
        <SectionHead eyebrow="Go further" title="Your people, your repositories, real history.">
          The same path queries, on who knows what, on any GitHub repository&apos;s decision records, and on decisions real teams later abandoned.
        </SectionHead>
        <div className={s.body}>
          <Group label="Go further">
            <Row href="/app/people/?graph=larkspur" title="What leaves when someone does"
              subtitle="Who knows why each decision was made, bus factor, bridges (betweenness) and knowledge islands (WCC)" />
            {repos.map(g => (
              <Row key={g.name} href={`/app/ledger/?graph=${g.name}`} title={`${g.title}, audited`}
                subtitle={`${g.decisions} decisions and the pull requests behind them, read with moot ingest-github`} />
            ))}
            {backtest && (
              <Row href={`/app/ledger/?graph=${backtest.name}&as_of=${backtest.as_of ?? ""}`} title={backtest.title}
                subtitle="Rewound month by month; graded by what their own maintainers later did" />
            )}
            <Row href="/app/ledger/?graph=larkspur&d=D01&tab=cypher" title="Every query behind one answer"
              subtitle="The read-only Cypher FalkorDB ran for D01, with rows and milliseconds" />
          </Group>
        </div>
      </div>
    </section>
  );
}
