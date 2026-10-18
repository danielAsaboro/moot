"use client";
// Try it: the live ask box in one calm card. Nothing is sent until the reader presses Ask or picks a question.
import { useRef, useState } from "react";
import EmptyState from "@/components/ui/EmptyState";
import { SearchField, SectionHead } from "@/components/ui";
import { api } from "@/lib/api";
import type { AskResponse } from "@/lib/types";
import TryAnswer from "./TryAnswer";
import s from "./TryIt.module.css";

const FIRST = "Why do we cap uploads at 10 MB?";
const SAMPLES = [
  "Can we deploy on a Friday?",
  "Why are EU customers served from Frankfurt only?",
  "Do we still need manual QA sign-off?",
  "What is our policy on blockchain?",
];

type State =
  | { kind: "idle" }
  | { kind: "loading"; question: string }
  | { kind: "done"; res: AskResponse }
  | { kind: "error"; message: string };

export default function TryIt() {
  const [question, setQuestion] = useState(FIRST);
  const [state, setState] = useState<State>({ kind: "idle" });
  const seq = useRef(0);

  const ask = (q: string) => {
    const text = q.trim();
    if (!text) return;
    const n = ++seq.current;
    setState({ kind: "loading", question: text });
    api.ask(text, { as_of: null, depth: 4 })
      .then(res => { if (n === seq.current) setState({ kind: "done", res }); })
      .catch((e: Error) => { if (n === seq.current) setState({ kind: "error", message: e.message }); });
  };

  const busy = state.kind === "loading";

  return (
    <section id="try" className={s.section} aria-label="Try it">
      <div className="wrap">
        <SectionHead eyebrow="Try it" title="Ask why a rule exists.">
          This box asks the live Larkspur graph. The answer comes with the path that decided it.
        </SectionHead>

        <div className={s.card}>
          <div className={s.askRow}>
            <div className={s.field}>
              <SearchField value={question} onChange={setQuestion} onSubmit={() => ask(question)}
                label="Question about a rule" placeholder="Ask why we do something" disabled={busy} />
            </div>
            <button type="button" className="btn" onClick={() => ask(question)} disabled={busy || !question.trim()}>
              {busy ? "Asking…" : "Ask"}
            </button>
          </div>

          <div className={s.samples} role="group" aria-label="Sample questions">
            {SAMPLES.map(q => (
              <button key={q} type="button" className="btn ghost small" disabled={busy}
                onClick={() => { setQuestion(q); ask(q); }}>{q}</button>
            ))}
          </div>

          <div className={s.out} aria-live="polite" aria-busy={busy}>
            {state.kind === "idle" && (
              <p className="t-footnote">Press Ask to see the verdict, the reason that decided it and the evidence behind it.</p>
            )}
            {state.kind === "loading" && (
              <div className={s.loading} role="status" aria-label={`Asking: ${state.question}`}>
                <div className="skeleton" style={{ width: 96, height: 28, borderRadius: 999 }} />
                <div className="skeleton" /><div className="skeleton" /><div className="skeleton" style={{ width: "60%" }} />
              </div>
            )}
            {state.kind === "error" && <EmptyState kind="error" title="Moot could not answer." detail={state.message}
              action={<button type="button" className="btn ghost small" onClick={() => ask(question)}>Try again</button>} />}
            {state.kind === "done" && <TryAnswer res={state.res} />}
          </div>
        </div>
      </div>
    </section>
  );
}
