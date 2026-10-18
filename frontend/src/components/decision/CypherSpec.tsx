"use client";
// The Queries tab: every read-only query FalkorDB ran for this answer, as a calm spec sheet. A query repeated with the
// same parameters (the audit runs once for the verdict and once for the gate) is shown once, with its run count.
import { useId, useMemo, useRef, useState } from "react";
import type { Query } from "@/lib/types";
import { Pill, cx } from "@/components/ui";
import EmptyState from "@/components/ui/EmptyState";
import { formatCypher } from "./CypherFormat";
import s from "./CypherSpec.module.css";

const ms = (n: number) => (n < 10 ? n.toFixed(2) : n.toFixed(1));
const msTotal = (n: number) => (n < 10 ? n.toFixed(1) : n.toFixed(0));
const keyOf = (q: Query) => `${q.cypher}\u0000${JSON.stringify(Object.entries(q.params ?? {}).sort(([a], [b]) => a.localeCompare(b)))}`;
const times = (n: number) => (n === 2 ? "twice" : `${n} times`);

interface Folded { q: Query; runs: number; ms: number; rows: number[] }

export default function CypherSpec({ queries }: { queries: Query[] }) {
  const total = queries.reduce((t, q) => t + (q.ms || 0), 0);
  const writes = queries.filter(q => q.write).length;
  const folded = useMemo(() => {
    const by = new Map<string, Folded>();
    for (const q of queries) {
      const k = keyOf(q);
      const f = by.get(k);
      if (f) { f.runs++; f.ms += q.ms || 0; f.rows.push(q.rows); }
      else by.set(k, { q, runs: 1, ms: q.ms || 0, rows: [q.rows] });
    }
    return [...by.values()];
  }, [queries]);

  if (!queries.length) {
    return <EmptyState kind="empty" title="No queries recorded for this answer." detail="Moot records every query it runs; this answer ran none." />;
  }
  const n = queries.length;
  const reads = n - writes;
  return (
    <section className={s.sheet} aria-label="Queries run for this answer">
      <p className={s.summary}>
        <span className="lead-in">
          {reads} read-only {reads === 1 ? "query" : "queries"} · {msTotal(total)} ms in the database · {writes ? `${writes} ${writes === 1 ? "write" : "writes"}` : "nothing written"}.
        </span>{" "}
        The model never sees or writes these.
      </p>
      {folded.length < n && (
        <p className="t-footnote">Repeats are folded, so {folded.length} distinct {folded.length === 1 ? "query is" : "queries are"} shown.</p>
      )}
      <ol className={s.list}>
        {folded.map((f, i) => <QueryCard key={i} f={f} n={i + 1} />)}
      </ol>
    </section>
  );
}

function QueryCard({ f, n }: { f: Folded; n: number }) {
  const { q, runs } = f;
  const lines = useMemo(() => formatCypher(q.cypher), [q.cypher]);
  const params = Object.entries(q.params ?? {});
  const id = useId();
  const rows = q.rows;
  const meta = [
    `${rows} ${rows === 1 ? "row" : "rows"}`,
    runs > 1 ? `${ms(f.ms / runs)} ms each` : `${ms(f.ms)} ms`,
    ...(runs > 1 ? [`ran ${times(runs)}`] : []),
  ].join(" · ");
  return (
    <li className={cx(s.card, q.write && s.write)}>
      <article aria-labelledby={id}>
        <header className={s.head}>
          <h3 id={id} className={s.title}>Query {n}</h3>
          {q.write && <Pill tone="moot">Writes</Pill>}
          <span className={cx("t-footnote", s.meta)}>{meta}</span>
          <CopyButton text={q.cypher} label={`query ${n}`} />
        </header>
        {params.length > 0 && (
          <dl className={s.params} aria-label="Parameters">
            {params.map(([k, v]) => (
              <div key={k}><dt className="id">${k}</dt><dd>{v === null ? "null" : typeof v === "string" ? v : JSON.stringify(v)}</dd></div>
            ))}
          </dl>
        )}
        <Code lines={lines} />
      </article>
    </li>
  );
}

function Code({ lines }: { lines: ReturnType<typeof formatCypher> }) {
  return (
    <pre className={s.code}><code>
      {lines.map((l, i) => (
        <span key={i} className={s.line}>
          {l.map((t, j) => (t.c === "text" || t.c === "punct" ? t.t : <span key={j} className={s[t.c]}>{t.t}</span>))}
          {"\n"}
        </span>
      ))}
    </code></pre>
  );
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<"idle" | "done" | "failed">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const copy = async () => {
    try {
      if (!navigator.clipboard) throw new Error("no clipboard");
      await navigator.clipboard.writeText(text);
      setState("done");
    } catch {
      setState("failed");
    }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), 2200);
  };
  return (
    <span className={s.copyWrap}>
      <button type="button" className={cx("btn plain", s.copy)} onClick={copy} aria-label={`Copy the Cypher of ${label}`}>
        {state === "done" ? "Copied" : "Copy"}
      </button>
      <span role="status" className={state === "failed" ? cx("t-footnote", s.copyFail) : "sr-only"}>
        {state === "failed" ? "Copy is blocked here. Select the text instead." : state === "done" ? "Copied to the clipboard." : ""}
      </span>
    </span>
  );
}
