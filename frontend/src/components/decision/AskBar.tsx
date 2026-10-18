"use client";
// The question field at the top of the ledger. Suggestions show only while it is focused and empty. "What if"
// questions go to the what-if view; everything else is answered by POST /api/ask at the current as-of and depth.
import { useEffect, useRef, useState, type FocusEvent } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAppState } from "@/lib/appState";
import { longDate } from "@/lib/format";
import { Group, Row, SearchField } from "@/components/ui";
import s from "./Ask.module.css";

const SAMPLES = [
  "Why do we cap uploads at 10 MB?",
  "Can we deploy on a Friday?",
  "Why are EU customers served from Frankfurt only?",
  "Do we still need manual QA sign-off?",
  "Who decided to rotate API keys every 90 days?",
  "What if we no longer need SOC 2?",
  "What is our policy on blockchain?",
];

const isWhatIf = (q: string) => /^\s*what\s+if\b/i.test(q);

export default function AskBar() {
  const { asOf, depth, select, setLastAsk, link } = useAppState();
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const closeTimer = useRef<number | null>(null);
  const [q, setQ] = useState("");
  const [focused, setFocused] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // "/" focuses the field from anywhere on the page that is not already a text field.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
      e.preventDefault();
      input.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => () => { if (closeTimer.current) window.clearTimeout(closeTimer.current); }, []);

  const ask = async (question: string) => {
    const text = question.trim();
    if (!text || busy) return;
    setError(null);
    setFocused(false);
    input.current?.blur();
    if (isWhatIf(text)) { router.push(link("/app/whatif/", { q: text })); return; }
    setBusy(true);
    try {
      const r = await api.ask(text, { as_of: asOf, depth });
      setLastAsk(r);
      // A matched decision opens below the answer; with no match the answer stands alone.
      select(r.audit ? r.audit.decision.id : null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  // Focus can move into the suggestions (Tab) without closing them; leaving the whole box closes them.
  const onFocusIn = () => {
    if (closeTimer.current) { window.clearTimeout(closeTimer.current); closeTimer.current = null; }
    setFocused(true);
  };
  const onFocusOut = (e: FocusEvent<HTMLDivElement>) => {
    if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
    closeTimer.current = window.setTimeout(() => setFocused(false), 120);
  };

  const open = focused && !q.trim() && !busy;
  return (
    <div className={s.bar} onFocus={onFocusIn} onBlur={onFocusOut}
      onKeyDown={e => { if (e.key === "Escape" && focused) { setFocused(false); input.current?.blur(); } }}>
      <SearchField value={q} onChange={v => { setQ(v); setError(null); }} onSubmit={() => void ask(q)}
        placeholder="Ask why we do something" label="Ask why the team does something" inputRef={input} />
      {busy && <p className={`t-footnote ${s.status}`} role="status">Looking in the graph…</p>}
      {error && <p className={`t-footnote ${s.error}`} role="alert"><span className="lead-in">Could not ask.</span> {error}</p>}
      {open && (
        // Pressing a suggestion must not blur the field first, or the list would close under the pointer.
        <div className={s.suggest} onMouseDown={e => e.preventDefault()}>
          <Group header="Try asking" label="Sample questions"
            footer={<span>Answers come from the graph as of {asOf ? longDate(asOf) : "today"}, depth {depth}. Start with “what if” to see what would fall.</span>}>
            {SAMPLES.map(t => (
              <Row key={t} title={t} clip onClick={() => { setQ(t); void ask(t); }}
                trailing={isWhatIf(t) ? <span className={`t-footnote ${s.tag}`}>What-if</span> : undefined} />
            ))}
          </Group>
        </div>
      )}
    </div>
  );
}
