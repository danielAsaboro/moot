"use client";
// /app/people: who only knows what. Knowing is read from authorship: owning a decision, writing its record, or writing
// dated evidence on a reason below it. The ranking, the bus factor, the knowledge islands (algo.WCC) and the bridges
// (algo.betweenness) are computed on a GRAPH.COPY with a KNOWS projection; "what leaves with them" removes the person
// from another copy. The company graph is never written. Everything here comes from GET /api/people,
// /api/people/{id}/departure and /api/spof.
import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAppState } from "@/lib/appState";
import { longDate, plural } from "@/lib/format";
import type { Query, Verdict } from "@/lib/types";
import { Group, Pill, Row, Sheet, StatCard, VerdictBadge } from "@/components/ui";
import EmptyState from "@/components/ui/EmptyState";
import CypherSpec from "@/components/decision/CypherSpec";
import s from "./people.module.css";

export interface PersonRow { id: string; name: string; role: string; knows: number; owns: string[]; sole: string[]; betweenness: number }
export interface PeopleResponse { as_of: string; people: PersonRow[]; bus_factor: { zero: string[]; one: string[]; more: number }; islands: number;
  orphaned_islands: string[][]; method: string; queries: Query[] }
export interface Departure { found: boolean; person: { id: string; name: string; role?: string }; as_of: string; active: boolean;
  leaves: { id: string; title: string; verdict: Verdict; systems: string[] }[];
  only_they_evidence: { id: string; text: string; evidence: string[]; decisions: string[] }[];
  owned: { id: string; title: string; verdict: Verdict }[]; systems_nobody_else_explains: string[];
  successor: { id: string; name: string; role: string } | null; method: string; queries: Query[] }
export interface Spof { as_of: string; total: number; reasons: { id: string; text: string; state: string; decisions: string[]; evidence: string[]; people: string[]; why: string }[] }

export default function PeopleView() {
  const { asOf, link } = useAppState();
  const { data, error, loading, reload } = useApi<PeopleResponse>(() => api.people(asOf), [asOf]);
  const spof = useApi<Spof>(() => api.spof(asOf), [asOf]);
  const [who, setWho] = useState<PersonRow | null>(null);
  const close = useCallback(() => setWho(null), []);

  if (loading && !data) return <div className={s.view}><div className="skeleton" style={{ width: 320, height: 40 }} /></div>;
  if (error && !data) {
    return <div className={s.view}><EmptyState kind="error" title="Could not load the people." detail={error}
      action={<button type="button" className="btn ghost small" onClick={reload}>Try again</button>} /></div>;
  }
  if (!data) return null;
  const one = data.bus_factor.one.length;
  const ranked = data.people.filter(p => p.knows > 0);

  return (
    <div className={s.view}>
      <header className={s.head}>
        <h1 className="t-large">{plural(one, "decision")} only one person here can explain.</h1>
        <p><span className="lead-in">Knowing why is read from what people wrote.</span> Someone knows a decision if they own it, wrote its
          record, or wrote dated evidence on a reason below it. Tap a person to see what would leave with them.</p>
      </header>

      <div className={s.stats}>
        <StatCard label="Bus factor 1" value={one} tone="moot" foot="live decisions one person here knows" />
        <StatCard label="Nobody left" value={data.bus_factor.zero.length} foot={data.bus_factor.zero.join(", ") || "every decision has a knower"} />
        <StatCard label="Knowledge islands" value={data.islands} foot="algo.WCC on the KNOWS projection" />
      </div>

      <Group header="Who only knows what" footer="Bridge is betweenness on the KNOWS projection: how much knowledge between other people runs through this one." label="People">
        {ranked.map(p => (
          <Row key={p.id} onClick={() => setWho(p)} ariaLabel={`What leaves with ${p.name}`}
            title={p.name}
            subtitle={<>{p.role} · knows {p.knows} · owns {p.owns.length}{p.sole.length > 0 && <> · only they know <span className="id">{p.sole.join(", ")}</span></>}</>}
            trailing={<span className={s.trail}>{p.sole.length > 0 && <Pill tone="moot">{p.sole.length} alone</Pill>}<span className={s.bridge}>bridge {Math.round(p.betweenness)}</span></span>} />
        ))}
      </Group>

      {spof.data && spof.data.reasons.length > 0 && (
        <Group header="Reasons with a single point of failure" footer="Two or more live decisions rest on each, and one document or one person still here vouches for it." label="Single points of failure">
          {spof.data.reasons.map(r => (
            <Row key={r.id} title={r.text} href={link("/app/whatif/", { premise: r.id })}
              subtitle={<><span className="id">{r.id}</span> · {r.why} · carries <span className="id">{r.decisions.join(", ")}</span></>} />
          ))}
        </Group>
      )}

      <details className={s.queries}>
        <summary className="t-footnote">The Cypher behind this page ({data.method})</summary>
        <CypherSpec queries={data.queries} />
      </details>

      <DepartureSheet person={who} asOf={asOf} onClose={close} />
    </div>
  );
}

/** What leaves with a person: the decisions, the reasons only they evidenced, the systems, who inherits what they own. */
export function DepartureBody({ data }: { data: Departure }) {
  const { link } = useAppState();
  const when = longDate(data.as_of);
  return (
        <div className={s.sheet}>
    <p className="t-body" style={{ margin: 0 }}>
      On {when}, {plural(data.leaves.length, "live decision")} would have nobody here who knows {data.leaves.length === 1 ? "its" : "their"} reasons.
    </p>
    {data.leaves.length > 0 && (
      <Group header="What leaves with them" onSurface>
        {data.leaves.map(d => (
          <Row key={d.id} href={link("/app/", { d: d.id })} title={d.title} subtitle={<span className="id">{d.id}</span>}
            trailing={<VerdictBadge verdict={d.verdict} />} />
        ))}
      </Group>
    )}
    {data.only_they_evidence.length > 0 && (
      <Group header="Reasons only they wrote evidence on" onSurface>
        {data.only_they_evidence.map(r => (
          <Row key={r.id} title={r.text} subtitle={<><span className="id">{r.evidence.join(", ")}</span> · under <span className="id">{r.decisions.join(", ")}</span></>} />
        ))}
      </Group>
    )}
    {data.systems_nobody_else_explains.length > 0 && (
      <p className="t-callout" style={{ margin: 0 }}><span className="lead-in">Systems nobody else can explain:</span> {data.systems_nobody_else_explains.join(", ")}.</p>
    )}
    {data.owned.length > 0 && (
      <p className="t-callout" style={{ margin: 0 }}>
        They own {plural(data.owned.length, "live decision")}; ownership would go up the reporting line to {data.successor ? data.successor.name : "nobody still here"}.
      </p>
    )}
    <p className="t-footnote" style={{ margin: 0 }}>Computed on a copy of the graph with {data.person.name} removed ({data.method}). The company graph is not written.</p>
        </div>
  );
}

function DepartureSheet({ person, asOf, onClose }: { person: PersonRow | null; asOf: string | null; onClose: () => void }) {
  const { data, error, loading } = useApi<Departure | null>(() => (person ? api.departure(person.id, asOf) : Promise.resolve(null)), [person?.id, asOf]);
  return (
    <Sheet open={!!person} title={person ? `If ${person.name} left` : ""} onClose={onClose} cancelLabel="Done">
      {loading && <div className="skeleton" style={{ width: "80%", height: 24 }} />}
      {error && <p role="alert">{error}</p>}
      {data && !loading && <DepartureBody data={data} />}
    </Sheet>
  );
}
