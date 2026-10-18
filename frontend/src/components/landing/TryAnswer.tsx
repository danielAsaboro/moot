"use client";
// One answer from /api/ask, inline in the Try it card: the verdict pill, the decision, the answer with its ids in mono,
// the path that decided it, how the answer was written, and a link into the ledger.
import { Fragment } from "react";
import Link from "next/link";
import EmptyState from "@/components/ui/EmptyState";
import { PathChain, StateTag, VerdictBadge, decidingEvent } from "@/components/ui";
import { longDate } from "@/lib/format";
import type { AskResponse, Premise } from "@/lib/types";
import s from "./TryIt.module.css";

/** Render "[PR-412]" citations and decision ids (D02) as mono ids. Text is otherwise shown as returned. */
function withIds(text: string) {
  return text.split(/(\[[^\]\s]{1,40}\]|\bD\d{2,3}\b)/g).map((part, i) => {
    const m = /^\[([^\]\s]{1,40})\]$/.exec(part) ?? /^(D\d{2,3})$/.exec(part);
    return m ? <span key={i} className="id">{m[1]}</span> : <Fragment key={i}>{part}</Fragment>;
  });
}

/** "2026-03-02" -> "2 Mar 2026"; only reformats dates already in the text. */
const prettyDates = (t: string) => t.replace(/\b\d{4}-\d{2}-\d{2}\b/g, m => longDate(m));

const NARRATION: Record<string, string> = {
  model: "Written from the query rows, then checked: every id it cites came back from a query.",
  template: "Written by a fixed template from the query rows.",
  structural: "Built from the graph structure alone.",
};

/** The reasons that decided the verdict: the broken ones, or else the first reason with evidence. */
function deciding(premises: Premise[]): Premise[] {
  const broken = premises.filter(p => p.state === "expired" || p.state === "disputed");
  if (broken.length) return broken.slice(0, 2);
  const withEv = premises.find(p => p.evidence.length);
  return withEv ? [withEv] : [];
}

export default function TryAnswer({ res }: { res: AskResponse }) {
  if (res.outcome === "unknown_entity" || res.outcome === "not_in_graph") {
    return (
      <EmptyState kind={res.outcome} title="That rule is not in the graph."
        detail="Moot does not guess. Ask about a rule Larkspur has on record, or pick one of the questions above." />
    );
  }

  const a = res.audit;
  // The pill already says the verdict; drop a leading "MOOT." from the text so it is said once.
  const text = a ? res.answer.replace(new RegExp(`^${a.verdict}\\.\\s*`), "") : res.answer;
  const paths = a ? deciding(a.premises) : [];
  const mode = res.narration ? NARRATION[res.narration] ?? null : null;

  return (
    <article className={s.answer} aria-label="Answer">
      {a && (
        <header className={s.head}>
          <VerdictBadge verdict={a.verdict} fill size="md" />
          <div className={s.decision}>
            <h3 className="t-title3">{a.decision.title}</h3>
            <p className="t-footnote">
              <span className="id">{a.decision.id}</span> · decided {longDate(a.decision.decided_on)} · as of {longDate(a.as_of)}
            </p>
          </div>
        </header>
      )}

      <p className={s.prose}>{withIds(prettyDates(text))}</p>

      {paths.map(p => (
        <div key={p.id} className={s.path}>
          <p className="t-footnote">
            <span className={s.state}><StateTag state={p.state} /></span>{" "}
            The reason {p.hops === 1 ? "one hop" : `${p.hops} hops`} from the decision
          </p>
          <PathChain path={p.path} evidence={decidingEvent(p.evidence)} />
        </div>
      ))}

      {res.outcome === "answered_from_memory" && res.memory && (
        <p className="t-footnote">Answered from finding <span className="id">{res.memory.id}</span>, recorded {longDate(res.memory.created_at)}.</p>
      )}

      <footer className={s.foot}>
        {mode && <p className="t-footnote">{mode}</p>}
        {a && <Link href={`/app/?q=${encodeURIComponent(res.question)}`} className="link">See the full answer <span aria-hidden="true">›</span></Link>}
      </footer>
    </article>
  );
}
