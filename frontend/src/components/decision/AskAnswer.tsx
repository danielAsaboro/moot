"use client";
// The answer to the last question, as a calm card above the decision. Citations in [brackets] were validated
// against the rows by the server; they render as ids, and a cited decision id opens that decision.
import type { ReactNode } from "react";
import type { AskResponse, Verdict } from "@/lib/types";
import { useAppState } from "@/lib/appState";
import { longDate } from "@/lib/format";
import { Card, VERDICT_WORD } from "@/components/ui";
import EmptyState from "@/components/ui/EmptyState";
import CypherSpec from "./CypherSpec";
import s from "./Ask.module.css";

const OUTCOME: Record<AskResponse["outcome"], string> = {
  answered_with_path: "Answered from the graph",
  answered_from_memory: "Answered from a recorded finding",
  not_in_graph: "Not in the graph",
  unknown_entity: "Nothing by that name",
};
const NARRATION: Record<string, string> = {
  model: "written up from the rows, every citation checked",
  structural: "no model call",
  template: "no model call",
};

function withCitations(text: string, open: (id: string) => void): ReactNode[] {
  return text.split(/(\[[A-Za-z0-9:_.\-]+\])/g).map((part, i) => {
    const m = /^\[([A-Za-z0-9:_.\-]+)\]$/.exec(part);
    if (!m) return part;
    const id = m[1];
    return /^D\d+$/.test(id)
      ? <button key={i} type="button" className={`id ${s.citeBtn}`} onClick={() => open(id)} aria-label={`Open ${id}`}>{id}</button>
      : <span key={i} className={`id ${s.cite}`}>{id}</span>;
  });
}

/** "MOOT. Cap file uploads…" → a bold "Moot." lead-in and the rest as the grey continuation. */
function splitLead(answer: string): [string | null, string] {
  const m = /^(MOOT|HOLDS|DISPUTED|UNDOCUMENTED|RETIRED)\.\s*/.exec(answer);
  return m ? [`${VERDICT_WORD[m[1] as Verdict]}.`, answer.slice(m[0].length)] : [null, answer];
}

function CloseButton({ onClick, className }: { onClick: () => void; className?: string }) {
  return (
    <button type="button" className={`${s.close} ${className ?? ""}`} onClick={onClick} aria-label="Close answer">
      <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><path d="M1.5 1.5l7 7M8.5 1.5l-7 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
    </button>
  );
}

export default function AskAnswer({ ask }: { ask: AskResponse }) {
  const { setLastAsk, select } = useAppState();
  const close = () => setLastAsk(null);
  const queries = ask.queries ?? [];

  if (ask.outcome === "unknown_entity" || ask.outcome === "not_in_graph") {
    return (
      <Card className={s.emptyCard} as="section">
        <CloseButton onClick={close} className={s.closeAbs} />
        <EmptyState kind={ask.outcome} title={ask.answer}
          detail={<>
            <span className={s.askedInline}>“{ask.question}”</span>{" "}
            Moot answers only from the graph. Nothing matched, so it says so instead of guessing.
          </>}
          action={queries.length > 0 ? (
            <details className={s.queries}>
              <summary className="btn plain">Show the query that ran</summary>
              <CypherSpec queries={queries} />
            </details>
          ) : undefined} />
      </Card>
    );
  }

  const mode = ask.narration ? NARRATION[ask.narration] : null;
  const mem = ask.memory;
  const [lead, rest] = splitLead(ask.answer);
  return (
    <Card as="section" className={s.card}>
      <div className={s.top}>
        <p className={`t-footnote ${s.outcome}`}>
          {[OUTCOME[ask.outcome], mode, ask.as_of ? `as of ${longDate(ask.as_of)}` : null].filter(Boolean).join(" · ")}
        </p>
        <CloseButton onClick={close} />
      </div>
      <h2 className={`t-headline ${s.asked}`}>“{ask.question}”</h2>
      <p className={s.answer}>
        {lead && <span className="lead-in">{lead} </span>}
        {withCitations(rest, select)}
      </p>
      {mem && (
        <p className="t-footnote" style={{ margin: 0 }}>
          From recorded finding <span className="id">{mem.id}</span>: {VERDICT_WORD[mem.verdict as Verdict] ?? mem.verdict} as of {longDate(mem.as_of)}, depth {mem.depth}.
        </p>
      )}
    </Card>
  );
}
