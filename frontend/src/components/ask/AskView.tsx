"use client";
// Ask: the app's front door. One search bar on an empty page; a question picks one read-only tool (POST /api/answer)
// and its rows come back as the one component that fits, under the tool step that shows what ran. The question lives
// in the URL (?q=…, or ?q=…&tool=…&id=… for a follow-up), so Back, reload and a shared link all show the same answer.
// ?d=D01 (every older link into /app) opens that decision's full panel under the bar.
import { useCallback, useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAppState } from "@/lib/appState";
import { useApi } from "@/lib/useApi";
import { longDate } from "@/lib/format";
import type { AnswerResponse, AnswerTool, LedgerResponse } from "@/lib/types";
import { cx } from "@/components/ui";
import EmptyState from "@/components/ui/EmptyState";
import DecisionPanel from "@/components/decision/DecisionPanel";
import ToolStep from "./ToolStep";
import { Answer, followUps, whyQuestion, type FollowUp } from "./Answers";
import s from "./ask.module.css";

// Example questions per graph: Kubernetes' own KEPs on its graph, the demo company's everywhere else
const K8S_STARTERS = [
  "Does KEP-3130 still hold?",
  "Who answers for KEP-3130?",
  "Can an agent change KEP-3130?",
  "Who knows why KEP-1205 was made?",
  "Show the evidence for KEP-3130",
];
const STARTERS = [
  "Why do we cap uploads at 10 MB?",
  "Can an agent change the Friday deploy freeze?",
  "What if we no longer need SOC 2?",
  "What did Ada own?",
  "Show the evidence for D17",
  "What leaves with Marcus?",
];
const ARG: Record<AnswerTool, string> = {
  audit_decision: "decision_id", check_action: "decision_id", evidence_packet: "decision_id", reopen_memo: "decision_id",
  decision_owner: "decision_id", what_if: "reason", orphaned_decisions: "person", ledger: "verdict", who_knows_why: "decision_id", departure: "person",
};

type State = { kind: "idle" } | { kind: "loading" } | { kind: "done"; res: AnswerResponse } | { kind: "error"; message: string };
interface Suggestion { q: string; tool?: AnswerTool; arg?: string }

export default function AskView() {
  const sp = useSearchParams();
  const router = useRouter();
  const { asOf, depth, link, graph } = useAppState();
  const q = sp.get("q") ?? "", tool = sp.get("tool") as AnswerTool | null, id = sp.get("id"), owner = sp.get("owner"), d = sp.get("d");
  const [state, setState] = useState<State>({ kind: "idle" });
  const [nonce, setNonce] = useState(0);
  const seq = useRef(0);
  const asked = !!(q || tool || d);

  useEffect(() => {
    if (!q && !tool) { setState({ kind: "idle" }); return; }
    const n = ++seq.current;
    setState({ kind: "loading" });
    const input = tool ? (owner ? { owner } : id ? { [ARG[tool]]: id } : {}) : undefined;
    api.answer({ question: q, tool, input, as_of: asOf, depth })
      .then(res => { if (n === seq.current) setState({ kind: "done", res }); })
      .catch((e: Error) => { if (n === seq.current) setState({ kind: "error", message: e.message }); });
  }, [q, tool, id, owner, asOf, depth, nonce]);

  const go = useCallback((f: Suggestion) => {
    const extra: Record<string, string> = { q: f.q };
    if (f.tool) { extra.tool = f.tool; if (f.arg) extra.id = f.arg; }
    router.push(link("/app/", extra));
  }, [router, link]);
  const follow = useCallback((f: FollowUp) => go({ q: f.q, tool: f.tool, arg: f.arg }), [go]);
  const reload = useCallback(() => setNonce(n => n + 1), []);

  return (
    <div className={cx(s.page, asked && s.asked)}>
      <section className={s.hero} aria-label="Ask Moot">
        {!asked && (
          <>
            <p className={s.eyebrow}>Ask Moot</p>
            <h1 className={s.h1}>Ask why your team does something. <span>See if it still holds.</span></h1>
            <p className={s.lead}>Ask about a rule, a reason or a person. Moot picks the right read-only tool, runs it against the graph and shows the answer it returns.</p>
          </>
        )}
        <AskBox key={q} initial="" onAsk={go} placeholder={asked ? "Ask another question" : graph?.startsWith("gh_kubernetes") ? "Does KEP-3130 still hold?" : "Why do we cap uploads at 10 MB?"} />
        {!asked && <Starters onAsk={go} />}
      </section>

      {d && !q && !tool && (
        <section className={s.exchange} aria-label="Decision">
          <div className={s.panel}><DecisionPanel id={d} /></div>
        </section>
      )}

      {(q || tool) && (
        <section className={s.exchange} aria-live="polite" aria-busy={state.kind === "loading"}>
          <h2 className={s.q}>{q}</h2>
          {state.kind === "error" ? (
            <EmptyState kind="error" title="The answer could not be loaded." detail={state.message}
              action={<button type="button" className="btn ghost small" onClick={reload}>Try again</button>} />
          ) : (
            <>
              {(state.kind === "loading" || (state.kind === "done" && state.res.tool)) && (
                <ToolStep res={state.kind === "done" ? state.res : null} running={state.kind === "loading"} tool={tool} />
              )}
              {state.kind === "loading" && <div className={cx("skeleton", s.skel)} />}
              {state.kind === "done" && (
                <>
                  <div className={s.answer}><Answer res={state.res} onAsk={follow} reload={reload} /></div>
                  <Next list={followUps(state.res)} onAsk={follow} />
                </>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}

function Starters({ onAsk }: { onAsk: (f: Suggestion) => void }) {
  const { asOf, link, graph } = useAppState();
  const starters = graph?.startsWith("gh_kubernetes") ? K8S_STARTERS : STARTERS;
  const { data } = useApi<LedgerResponse>(() => api.ledger({ as_of: asOf }), [asOf]);
  const moot = data?.decisions.filter(r => r.verdict === "MOOT").length;
  return (
    <>
      <div className={s.chips} role="group" aria-label="Example questions">
        {starters.map(t => <button key={t} type="button" className={s.chip} onClick={() => onAsk({ q: t })}>{t}</button>)}
      </div>
      {data && <p className={s.meta}>{data.decisions.length} decisions, checked against dated evidence as of {longDate(data.as_of)}. {moot} are moot.</p>}
      <Link href={link("/app/ledger/")} className={cx("link", s.browse)}>Or browse all {data ? data.decisions.length : ""} decisions <span aria-hidden="true">›</span></Link>
    </>
  );
}

function Next({ list, onAsk }: { list: FollowUp[]; onAsk: (f: FollowUp) => void }) {
  if (!list.length) return null;
  return (
    <div className={s.next} role="group" aria-label="Ask next">
      <p className={s.lbl}>Ask next</p>
      {list.map(f => <button key={f.q} type="button" className={s.chip} onClick={() => onAsk(f)}>{f.q}</button>)}
    </div>
  );
}

/** The search bar. While typing, suggestions come from the graph's own full-text resolver (GET /api/search). */
function AskBox({ initial, onAsk, placeholder }: { initial: string; onAsk: (f: Suggestion) => void; placeholder: string }) {
  const [text, setText] = useState(initial);
  const [opts, setOpts] = useState<Suggestion[]>([]);
  const [sel, setSel] = useState(-1);
  const [open, setOpen] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
      e.preventDefault(); input.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const t = text.trim();
    if (t.length < 3) { setOpts([]); return; }
    let live = true;
    const timer = window.setTimeout(() => {
      api.search(t).then(rows => {
        if (!live) return;
        setOpts(rows.filter(r => r.matched_terms > 0).slice(0, 5).map(r => ({ q: whyQuestion(r.title), tool: "audit_decision", arg: r.id })));
        setSel(-1);
      }).catch(() => { if (live) setOpts([]); });
    }, 140);
    return () => { live = false; window.clearTimeout(timer); };
  }, [text]);

  const submit = () => {
    if (open && sel >= 0 && opts[sel]) { onAsk(opts[sel]); return; }
    const t = text.trim();
    if (t) { setOpen(false); input.current?.blur(); onAsk({ q: t }); }
  };
  const show = open && opts.length > 0;
  return (
    <form className={s.box} role="search" onSubmit={e => { e.preventDefault(); submit(); }}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
      <input ref={input} value={text} onChange={e => { setText(e.target.value); setOpen(true); }} placeholder={placeholder}
        aria-label="Ask Moot" role="combobox" aria-expanded={show} aria-controls={listId} aria-autocomplete="list"
        aria-activedescendant={show && sel >= 0 ? `${listId}-${sel}` : undefined}
        onFocus={() => setOpen(true)} onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onKeyDown={e => {
          if (!show) return;
          if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); setSel(i => (i + (e.key === "ArrowDown" ? 1 : -1) + opts.length) % opts.length); }
          else if (e.key === "Escape") setOpen(false);
        }} />
      <button type="submit" className={s.go} disabled={!text.trim()} aria-label="Ask">
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </button>
      {show && (
        <ul className={s.sugg} id={listId} role="listbox" aria-label="Suggestions">
          {opts.map((o, i) => (
            <li key={o.q} id={`${listId}-${i}`} role="option" aria-selected={i === sel} onMouseDown={e => { e.preventDefault(); onAsk(o); }}>
              <span className={s.sk}>Why</span><span className={s.st}>{o.q}</span>
            </li>
          ))}
        </ul>
      )}
    </form>
  );
}
