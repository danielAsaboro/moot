"use client";
// The tool step above an answer: which read-only tool ran, why it was picked, its input, and every query it sent to
// FalkorDB with rows and time. Running while the request is in flight, Completed when the rows are back.
import { useId, useState } from "react";
import type { AnswerResponse, Query } from "@/lib/types";
import { formatCypher } from "@/components/decision/CypherFormat";
import { cx } from "@/components/ui";
import s from "./ask.module.css";

const WORD = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];
const count = (n: number, one: string, many: string) => `${n < WORD.length ? WORD[n] : n} ${n === 1 ? one : many}`;
const PICKED = { rules: "Picked by the rules", model: "Picked by a model from the tool list", you: "You picked this follow-up" } as const;

function Cypher({ q }: { q: Query }) {
  return (
    <pre className={s.cypher}>
      {formatCypher(q.cypher).map((line, i) => (
        <span key={i} className={s.cline}>{line.map((t, j) => <span key={j} className={s[`k_${t.c}`]}>{t.t}</span>)}{"\n"}</span>
      ))}
    </pre>
  );
}

export default function ToolStep({ res, running, tool }: { res: AnswerResponse | null; running: boolean; tool?: string | null }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const name = res?.tool ?? tool ?? "picking a tool";
  const qs = res?.queries ?? [];
  const rows = qs.reduce((n, q) => n + q.rows, 0), ms = qs.reduce((n, q) => n + q.ms, 0);
  const summary = running ? "running against the graph" : res ? `${count(qs.length, "query", "queries")} · ${rows} ${rows === 1 ? "row" : "rows"} · ${ms.toFixed(1)} ms` : "";
  return (
    <div className={s.step} data-open={open || undefined}>
      <button type="button" className={s.stepHead} onClick={() => setOpen(o => !o)} aria-expanded={open} aria-controls={id} disabled={!res}>
        <svg className={s.chev} width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><path d="M3 1.5 6.5 5 3 8.5" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
        <span className={cx("id", s.tname)}>{name}</span>
        <span className={s.sum}>{summary}</span>
        <span className={cx(s.state, running ? s.run : s.done)}>{running ? "Running" : "Completed"}</span>
      </button>
      {open && res && (
        <div className={s.stepBody} id={id}>
          <div>
            <p className={s.lbl}>{PICKED[res.picked_by]}</p>
            <p>Because {res.why}{res.matched ? `; ${res.matched}` : ""}. The model, when there is one, only picks the tool and fills in its input; it never writes a query.</p>
          </div>
          <div>
            <p className={s.lbl}>Input</p>
            <pre className={s.cypher}>{`${res.tool}(${JSON.stringify({ ...res.input, as_of: res.as_of })})`}</pre>
          </div>
          <div>
            <p className={s.lbl}>The read-only queries it ran</p>
            <ol className={s.queries}>
              {qs.map((q, i) => (
                <li key={i}>
                  <span className={s.qmeta}>{q.rows} {q.rows === 1 ? "row" : "rows"} · {q.ms} ms</span>
                  <Cypher q={q} />
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </div>
  );
}
