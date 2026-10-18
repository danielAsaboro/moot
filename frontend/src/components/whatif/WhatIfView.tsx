"use client";
// /app/whatif/: pretend one written-down reason broke today and show which decisions would fall, through which chain.
// The what-if itself is read-only; "Post it as a change" writes one evidence node to the visitor's own sandbox copy (moot/sandbox.py).
import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAppState } from "@/lib/appState";
import { longDate, plural } from "@/lib/format";
import type { WhatIfDecision, WhatIfResponse } from "@/lib/types";
import { Card, Group, Row, SearchField, VerdictBadge, cx } from "@/components/ui";
import EmptyState from "@/components/ui/EmptyState";
import CypherSpec from "@/components/decision/CypherSpec";
import WhatIfWiring from "./WhatIfWiring";
import RiskyTable from "./RiskyTable";
import s from "./whatif.module.css";

const NO_MATCH = "No reason in the graph matches that.";
const NO_MATCH_DETAIL = "Moot only tests reasons someone wrote down. Try other words, or pick one of the riskiest reasons below.";

export default function WhatIfView() {
  const sp = useSearchParams();
  const router = useRouter();
  const { asOf, depth, link } = useAppState();
  const q = sp.get("q")?.trim() ?? "";
  const premise = sp.get("premise")?.trim() ?? "";
  const [text, setText] = useState(q);
  const results = useRef<HTMLDivElement>(null);
  useEffect(() => { setText(q); }, [q]);

  const res = useApi<WhatIfResponse | null>(async () => {
    if (!q && !premise) return null;
    const view = { as_of: asOf, depth };
    try {
      if (premise && q) {
        // A picked candidate: test it, and keep the other matches for the question on screen.
        const [r, c] = await Promise.all([api.whatif({ premise, ...view }), api.whatif({ q, ...view }).catch(() => null)]);
        return { ...r, candidates: c?.candidates ?? [], question: q };
      }
      return await api.whatif(premise ? { premise, ...view } : { q, ...view });
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return { found: false, question: q || premise, candidates: [], answer: NO_MATCH };
      throw e;
    }
  }, [q, premise, asOf, depth]);
  const risky = useApi(() => api.risky({ as_of: asOf, depth }), [asOf, depth]);

  const go = (extra: Record<string, string>) => router.push(link("/app/whatif/", extra), { scroll: false });
  const submit = () => {
    const t = text.trim();
    if (t) go({ q: t });
  };
  const testRisky = (id: string) => {
    go({ premise: id });
    const reduce = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    results.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  };

  const data = res.data;
  const tested = data?.found ? data.premise?.id ?? null : null;

  return (
    <div className={s.page}>
      <header className={s.head}>
        <h1 className={cx("t-large", s.h1)}>What if a reason broke today?</h1>
        <div className={s.search}>
          <SearchField value={text} onChange={setText} onSubmit={submit} label="A reason to test"
            placeholder="What if we no longer need SOC 2?" />
        </div>
      </header>

      <div ref={results} className={s.results} aria-live="polite" aria-busy={res.loading}>
        {!q && !premise ? (
          <EmptyState kind="nothing_selected" title="No reason tested yet."
            detail="Type what might stop being true, or pick one of the riskiest reasons below." />
        ) : res.loading && !data ? (
          <ResultSkeleton />
        ) : res.error ? (
          <EmptyState kind="error" title="The what-if could not run." detail={res.error}
            action={<button type="button" className="btn ghost small" onClick={res.reload}>Try again</button>} />
        ) : data && !data.found ? (
          <EmptyState kind="unknown_entity" title={NO_MATCH} detail={NO_MATCH_DETAIL} />
        ) : data?.found && data.premise ? (
          <Result data={data} q={q} pick={id => go({ q, premise: id })} stale={res.loading} />
        ) : null}
      </div>

      <section className={s.risky} aria-labelledby="risky-head">
        <div className={s.riskyHead}>
          <h2 id="risky-head" className="t-title2">Riskiest reasons</h2>
          <p className="t-sub">
            <span className="lead-in">The reasons the most rules rest on.</span> Tap one to test it.
          </p>
        </div>
        {risky.loading && !risky.data ? (
          <div className={s.skelRows} aria-hidden="true">{[0, 1, 2, 3, 4].map(i => <div key={i} className="skeleton" style={{ height: 22 }} />)}</div>
        ) : risky.error ? (
          <EmptyState kind="error" title="The ranking could not load." detail={risky.error}
            action={<button type="button" className="btn ghost small" onClick={risky.reload}>Try again</button>} />
        ) : risky.data && risky.data.reasons.length ? (
          <RiskyTable data={risky.data} current={tested} onTest={testRisky} />
        ) : (
          <EmptyState kind="empty" title="No reasons in the graph to rank." />
        )}
      </section>
    </div>
  );
}

/** "2 hops · via “The SOC 2 auditor requires…”", from the path rows. */
function via(d: WhatIfDecision): string {
  const mid = d.path.slice(1, -1);
  if (!mid.length) return "Rests on it directly";
  const more = mid.length > 1 ? ` and ${plural(mid.length - 1, "more reason")}` : "";
  return `${plural(d.hops, "hop")} · via “${mid[0].title}”${more}`;
}

function Result({ data, q, pick, stale }: { data: WhatIfResponse; q: string; pick: (id: string) => void; stale: boolean }) {
  const { link, asOf } = useAppState();
  const premise = data.premise!;
  const decisions = data.decisions ?? [];
  const fall = data.would_fall ?? 0;
  const already = data.already_moot ?? 0;
  const cands = data.candidates ?? [];
  const when = asOf ? `on ${longDate(asOf)}` : "today";
  return (
    <div className={cx(s.result, stale && s.stale)}>
      {q && cands.length > 1 && (
        <div className={s.cands}>
          <p className="t-footnote">{cands.length} reasons match “{q}”. Pick the one to test.</p>
          <div className={s.chips}>
            {cands.map(c => (
              <button key={c.id} type="button" className={cx("btn small", c.id !== premise.id && "ghost", s.chip)}
                onClick={() => pick(c.id)} aria-pressed={c.id === premise.id}>
                {c.text}
              </button>
            ))}
          </div>
        </div>
      )}

      <Card as="section" className={s.card}>
        <h2 className={s.headline}>
          If “{premise.text}” broke {when},{" "}
          {fall === 0
            ? "no standing decision would fall."
            : <span className={s.fall}>{plural(fall, "standing decision")} would fall.</span>}
        </h2>
        {(already > 0 || (fall === 0 && decisions.length > 0)) && (
          <p className="t-sub">
            {plural(decisions.length, "decision")} rest on it; {already} {already === 1 ? "is" : "are"} already moot.
          </p>
        )}

        {decisions.length ? (
          <>
            <WhatIfWiring premise={premise} decisions={decisions} asOf={data.as_of ?? ""} depth={data.depth ?? 4} />
            <Group onSurface label="Decisions resting on this reason">
              {decisions.map(d => (
                <Row key={d.id} href={link("/app/", { d: d.id })} title={d.title} subtitle={<span className={s.via}>{via(d)}</span>}
                  trailing={
                    <span className={s.flip}>
                      {d.flips ? (
                        <>
                          <VerdictBadge verdict={d.before} />
                          <span className={s.arrow} aria-label="becomes">→</span>
                          <VerdictBadge verdict={d.after} />
                        </>
                      ) : <VerdictBadge verdict={d.after} />}
                    </span>
                  } />
              ))}
            </Group>
          </>
        ) : (
          <EmptyState kind="empty" title="No decision rests on this reason at this depth."
            detail="Raise the depth to follow longer chains, or test another reason." />
        )}

        <p className="t-footnote">A read-only path query. Nothing is written to the graph.</p>
        <PostChange premiseId={premise.id} premiseText={premise.text} />
        {data.queries && data.queries.length > 0 && (
          <details className={s.queries}>
            <summary className={s.summary}>Show queries</summary>
            <CypherSpec queries={data.queries} />
          </details>
        )}
      </Card>
    </div>
  );
}

/** Apply the break for real, in the visitor's own scratch copy of the graph, then Reset. The company graph is only read. */
function PostChange({ premiseId, premiseText }: { premiseId: string; premiseText: string }) {
  const { asOf } = useAppState();
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [made, setMade] = useState<Awaited<ReturnType<typeof api.postChange>> | null>(null);
  useEffect(() => { setMade(null); setErr(null); }, [premiseId]);
  const apply = async () => {
    setBusy(true); setErr(null);
    try { setMade(await api.postChange({ premise: premiseId, rel: "CONTRADICTS", at: asOf, title: title || `“${premiseText}” no longer holds` }, asOf)); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const reset = async () => { if (made) { await api.resetChange(made.sandbox).catch(() => null); setMade(null); } };
  return (
    <div className={s.post}>
      {!made ? (
        <form onSubmit={e => { e.preventDefault(); apply(); }} className={s.postForm}>
          <label className="t-footnote" htmlFor="moot-post">Post it as a change, in your own copy of the graph:</label>
          <input id="moot-post" className={s.postInput} value={title} onChange={e => setTitle(e.target.value)}
            placeholder="What happened, e.g. “We stopped selling to enterprise customers”" maxLength={200} />
          <button type="submit" className="btn small" disabled={busy}>{busy ? "Applying…" : "Apply"}</button>
        </form>
      ) : (
        <div className={s.postDone}>
          <p className="t-footnote">
            Applied to sandbox <code>{made.sandbox}</code> on {longDate(made.at)}: {made.changed.length
              ? `${plural(made.changed.length, "decision")} changed verdict.` : "no verdict changed."} The company graph was not touched.
          </p>
          {made.changed.length > 0 && (
            <ul className={s.postList}>
              {made.changed.map(c => (
                <li key={c.id}><VerdictBadge verdict={c.before} /> <span aria-label="becomes">→</span> <VerdictBadge verdict={c.after} />{" "}
                  {c.title} <span className="t-footnote">(gate {c.gate_before} → {c.gate_after})</span></li>
              ))}
            </ul>
          )}
          <p className="t-footnote">
            <a className="link" href={`/app/ledger/?graph=${made.sandbox}`}>Open the ledger in the sandbox</a> ·{" "}
            <button type="button" className="link" onClick={reset}>Reset</button> · it expires in an hour.
          </p>
        </div>
      )}
      {err && <p className="t-footnote" role="alert">{err}</p>}
    </div>
  );
}

function ResultSkeleton() {
  return (
    <Card className={s.card}>
      <span className="sr-only" role="status">Following the paths…</span>
      <div className="skeleton" style={{ height: 30, width: "80%" }} />
      <div className="skeleton" style={{ height: 30, width: "50%" }} />
      <div className="skeleton" style={{ height: 180 }} />
    </Card>
  );
}
