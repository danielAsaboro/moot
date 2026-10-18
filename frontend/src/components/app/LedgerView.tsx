"use client";
// The ledger (/app/ledger/): every decision at once, for browsing. Desktop: the ledger column on the left, the answer and the selected decision on the right.
// Phone (<= 960px): a pushed view. With a decision (or an answer) open, only the detail shows, with a back button;
// otherwise only the ledger.
import { useEffect, useLayoutEffect, useRef } from "react";
import Link from "next/link";
import { useAppState } from "@/lib/appState";
import DecisionPanel from "@/components/decision/DecisionPanel";
import LedgerPane from "@/components/app/LedgerPane";
import EmptyState from "@/components/ui/EmptyState";
import s from "./ledgerView.module.css";

const PHONE = "(max-width: 960px)";

export default function LedgerView() {
  const { selected, select, link } = useAppState();
  const pushed = !!selected;

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

  const back = () => select(null);

  return (
    <div className={s.page} data-pushed={pushed ? "true" : undefined}>
      <section className={s.left} aria-label="Decision ledger"><LedgerPane /></section>
      <section className={s.right} aria-label={selected ? "Selected decision" : "Answer"}>
        <button type="button" className={s.back} onClick={back} aria-label="Back to the ledger">
          <svg width="11" height="18" viewBox="0 0 11 18" aria-hidden="true"><path d="M9 2L2 9l7 7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
          Ledger
        </button>
        {selected ? <DecisionPanel id={selected} /> : (
          <div className={s.empty}>
            <EmptyState kind="nothing_selected" title="Choose a decision."
              detail={<>Pick one to see its verdict and the path that proves it, or <Link href={link("/app/")} className="link">ask a question</Link>.</>} />
          </div>
        )}
      </section>
    </div>
  );
}
