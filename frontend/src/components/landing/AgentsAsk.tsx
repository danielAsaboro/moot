"use client";
// Landing section 7: agents ask the gate before they act. The card is the live answer for D01 from /api/gate.
import { Fragment, type ReactNode } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { GateBadge } from "@/components/ui";
import { longDate } from "@/lib/format";
import type { GateReason } from "@/lib/types";
import s from "./AgentsAsk.module.css";

const ID = "D01";
const AS_OF = "2026-10-16";

/** The reason sentence as the API wrote it, with ISO dates read aloud and the ids it names set in mono. */
function ReasonText({ reason, ids }: { reason: GateReason; ids: string[] }) {
  const names = [...new Set([...ids, reason.evidence].filter((x): x is string => Boolean(x)))].map(x => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const re = new RegExp(`(\\d{4}-\\d{2}-\\d{2}${names.length ? `|\\b(?:${names.join("|")})\\b` : ""})`, "g");
  const text = reason.text.replace(/"([^"]*)"/g, "“$1”");
  const out: ReactNode[] = text.split(re).map((part, i) => {
    if (i % 2 === 0) return <Fragment key={i}>{part}</Fragment>;
    if (/^\d{4}-\d{2}-\d{2}$/.test(part)) return <Fragment key={i}>{longDate(part)}</Fragment>;
    return <span key={i} className="id">{part}</span>;
  });
  return <>{out}</>;
}

export default function AgentsAsk() {
  const { data, error, loading } = useApi(() => api.gate(ID, AS_OF), []);
  const ids = data ? [data.decision_id, ...data.reasons.flatMap(r => (r.evidence ? [r.evidence] : []))] : [];
  return (
    <section id="gate" className={s.section} aria-labelledby="gate-title">
      <div className={`wrap ${s.grid}`}>
        <div className={s.text}>
          <div className="t-eyebrow">For agents</div>
          <h2 id="gate-title" className="t-display">Agents ask first.</h2>
          <p className={s.lead}>
            <span className="lead-in">Before an agent enforces, relies on or renews a rule, it asks the graph.</span> The answer
            is Allow, Deny or Revalidate, with the path that decided it.
          </p>
        </div>

        <div className={s.card} aria-live="polite" aria-busy={loading || undefined}>
          {loading && (
            <>
              <div className="skeleton" style={{ width: "70%" }} />
              <div className="skeleton" style={{ width: 120, height: 48, borderRadius: "var(--r-pill)" }} />
              <div className="skeleton" />
              <div className="skeleton" style={{ width: "85%" }} />
            </>
          )}
          {error && (
            <>
              <p className={s.question}>The gate could not be reached.</p>
              <p className="t-footnote">{error}</p>
            </>
          )}
          {data && (
            <>
              <p className={s.question}>Can an agent act on <span className="lead-in">{data.title ?? data.decision_id}</span>?</p>
              <div className={s.answer}>
                <GateBadge gate={data.gate} size="lg" />
                <span className="t-sub">checked at depth {data.depth}</span>
              </div>
              <ul className={s.rows}>
                {data.reasons.map((r, i) => (
                  <li key={`${r.code}-${i}`} className={s.row}><ReasonText reason={r} ids={ids} /></li>
                ))}
                {data.reasons.length === 0 && <li className={s.row}>No reason to stop it.</li>}
                <li className={s.row}>
                  One call: <code className="id">GET /api/gate/{data.decision_id}</code>, or the MCP tool <code className="id">check_action</code>.
                </li>
              </ul>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
