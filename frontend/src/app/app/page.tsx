"use client";
// The ledger view. Desktop: the ledger column on the left, the answer and the selected decision on the right.
// Phone (<= 960px): a pushed view. With a decision (or an answer) open, only the detail shows, with a back button;
// otherwise only the ledger.
import { useEffect, useLayoutEffect, useRef } from "react";
import { useAppState } from "@/lib/appState";
import AskAnswer from "@/components/decision/AskAnswer";
import DecisionPanel from "@/components/decision/DecisionPanel";
import LedgerPane from "@/components/app/LedgerPane";
import EmptyState from "@/components/ui/EmptyState";
import s from "./ledger.module.css";

const PHONE = "(max-width: 960px)";

export default function LedgerPage() {
  const { selected, lastAsk, select, setLastAsk } = useAppState();
  const pushed = !!selected || !!lastAsk;

  // Phone: remember where the reader was in the ledger, open the detail at its top, and come back to the same place.
  const ledgerY = useRef(0);
  const wasPushed = useRef(pushed);
  useEffect(() => {
    const onScroll = () => { if (!wasPushed.current) ledgerY.current = window.scrollY; };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  useLayoutEffect(() => {
    if (wasPushed.current === pushed) return;
    wasPushed.current = pushed;
    if (!window.matchMedia(PHONE).matches) return;
    window.scrollTo(0, pushed ? 0 : ledgerY.current);
  }, [pushed]);

  const back = () => { setLastAsk(null); select(null); };

  return (
    <div className={s.page} data-pushed={pushed ? "true" : undefined}>
      <section className={s.left} aria-label="Decision ledger"><LedgerPane /></section>
      <section className={s.right} aria-label={selected ? "Selected decision" : "Answer"}>
        <button type="button" className={s.back} onClick={back} aria-label="Back to the ledger">
          <svg width="11" height="18" viewBox="0 0 11 18" aria-hidden="true"><path d="M9 2L2 9l7 7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
          Ledger
        </button>
        {lastAsk && <AskAnswer ask={lastAsk} />}
        {selected ? <DecisionPanel id={selected} /> : !lastAsk && (
          <div className={s.empty}>
            <EmptyState kind="nothing_selected" title="Choose a decision."
              detail="Or ask why the team does something. Every verdict comes with the path that proves it." />
          </div>
        )}
      </section>
    </div>
  );
}
