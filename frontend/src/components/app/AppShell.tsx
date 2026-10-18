"use client";
// The /app frame: a quiet blurred bar with the wordmark, the section nav as capsule links, a "Graph" capsule (which
// company or repository to audit, and the GitHub connector), an "As of" capsule that opens the view settings (date and
// depth: a popover on wide screens, a sheet on phones) and the theme toggle.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useAppState } from "@/lib/appState";
import { api, type GraphsResponse } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { longDate } from "@/lib/format";
import { Segmented, Sheet, ThemeToggle, Wordmark, cx } from "@/components/ui";
import ShellPortal from "./ShellPortal";
import s from "./shell.module.css";

const NAV: [string, string][] = [
  ["/app/", "Ask"],
  ["/app/ledger/", "Ledger"],
  ["/app/map/", "Map"],
  ["/app/gate/", "Agent gate"],
  ["/app/orphans/", "Owners"],
  ["/app/people/", "People"],
  ["/app/whatif/", "What-if"],
  ["/app/realworld/", "Real world"],
];

const DEPTHS: ["1" | "2" | "3" | "4", string][] = [["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"]];

function usePhone(query = "(max-width: 640px)") {
  const [on, setOn] = useState(false);
  useEffect(() => {
    const m = window.matchMedia(query);
    const sync = () => setOn(m.matches);
    sync();
    m.addEventListener("change", sync);
    return () => m.removeEventListener("change", sync);
  }, [query]);
  return on;
}

/** Date, "Today" and depth: the same controls in the popover and in the phone sheet. */
function ViewSettings() {
  const { asOf, setAsOf, depth, setDepth } = useAppState();
  const dateId = useId();
  return (
    <div className={s.settings}>
      <div className={s.setRow}>
        <label htmlFor={dateId} className={s.setLabel}>As of</label>
        <div className={s.setCtl}>
          <input id={dateId} className={cx("input", s.date)} type="date" value={asOf ?? ""}
            onChange={e => setAsOf(e.target.value || null)} />
          <button type="button" className={cx("btn", "plain", s.today)} onClick={() => setAsOf(null)} disabled={!asOf}>Today</button>
        </div>
      </div>
      <div className={s.setRow}>
        <span className={s.setLabel}>Depth</span>
        <div className={s.setCtl}>
          <Segmented label="Depth" value={String(Math.min(4, depth)) as "1" | "2" | "3" | "4"} options={DEPTHS}
            onChange={v => setDepth(Number(v))} />
        </div>
      </div>
      <p className={cx("t-footnote", s.setNote)}>
        Depth is how many reasons deep Moot follows from each decision. The date shows the ledger as it stood then.
      </p>
    </div>
  );
}

function AsOfMenu() {
  const { asOf, depth } = useAppState();
  const phone = usePhone();
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const popId = useId();

  // The popover closes on Escape (focus goes back to the button) and on a press outside it.
  useEffect(() => {
    if (!open || phone) return;
    pop.current?.querySelector<HTMLElement>("input, button")?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); btn.current?.focus(); } };
    const onDown = (e: PointerEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("pointerdown", onDown); };
  }, [open, phone]);

  const label = asOf ? longDate(asOf) : "Today";
  return (
    <div ref={wrap} className={s.asof}>
      <button ref={btn} type="button" className={s.capsule} onClick={() => setOpen(o => !o)}
        aria-expanded={open} aria-controls={open && !phone ? popId : undefined} aria-haspopup="dialog"
        aria-label={`As of ${asOf ? longDate(asOf) : "today"}, depth ${depth}. Change`}>
        <span className={s.capLabel}>{label}</span>
        {depth !== 4 && <span className={s.capDepth}>· depth {depth}</span>}
        <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true" className={s.caret}><path d="M2 3.5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </button>
      {phone ? (
        <ShellPortal><Sheet open={open} title="Date and depth" onClose={() => setOpen(false)} cancelLabel="Done"><ViewSettings /></Sheet></ShellPortal>
      ) : open && (
        <div ref={pop} id={popId} className={s.popover} role="dialog" aria-label="As of and depth"><ViewSettings /></div>
      )}
    </div>
  );
}

const KIND: Record<string, string> = { demo: "Demo company", real: "Real ADRs", backtest: "Backtest", github: "GitHub repository" };

/** Which graph the whole app reads: the demo company, the real public ADRs, the backtest or an ingested repository. */
function GraphPicker({ data, onDone }: { data: GraphsResponse | null; onDone: () => void }) {
  const { graph, setGraphName } = useAppState();
  const [repo, setRepo] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const current = graph ?? data?.graphs.find(x => x.default)?.name;
  const ingest = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await api.ingestGithub(repo.trim());
      setMsg(`${r.decisions} decisions from ${r.folder}, ${r.pull_requests} pull requests, ${r.people} people.`);
      setGraphName(r.graph); onDone();
    } catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className={s.settings}>
      <ul className={s.graphs} aria-label="Graphs">
        {(data?.graphs ?? []).map(x => (
          <li key={x.name}>
            <button type="button" className={cx(s.graphRow, x.name === current && s.graphOn)} aria-pressed={x.name === current}
              onClick={() => { setGraphName(x.default ? null : x.name); onDone(); }}>
              <span className={s.graphTitle}>{x.title}</span>
              <span className={s.graphSub}>{KIND[x.kind] ?? x.kind} · {x.decisions} decisions</span>
            </button>
          </li>
        ))}
      </ul>
      <form className={s.ingest} onSubmit={e => { e.preventDefault(); if (repo.trim()) ingest(); }}>
        <label className={s.setLabel} htmlFor="moot-ingest">Audit a GitHub repository</label>
        {data?.ingest ? (
          <div className={s.setCtl}>
            <input id="moot-ingest" className={cx("input", s.date)} placeholder="owner/repo" value={repo} onChange={e => setRepo(e.target.value)} disabled={busy} />
            <button type="submit" className={cx("btn", "ghost")} disabled={busy || !repo.trim()}>{busy ? "Reading…" : "Ingest"}</button>
          </div>
        ) : (
          <p className={cx("t-footnote", s.setNote)}>This deployment is read-only. Locally: <code className="id">moot ingest-github owner/repo</code> reads its ADR folder and pull requests into a new graph.</p>
        )}
        {msg && <p className={cx("t-footnote", s.setNote)} role="status">{msg}</p>}
      </form>
    </div>
  );
}

function GraphMenu() {
  const { graph } = useAppState();
  const { data } = useApi(() => api.graphs(), []);
  const phone = usePhone();
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open || phone) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    const onDown = (e: PointerEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("pointerdown", onDown); };
  }, [open, phone]);
  const info = data?.graphs.find(x => (graph ? x.name === graph : x.default));
  const label = info ? (info.kind === "demo" ? "Larkspur" : info.title) : graph ?? "Larkspur";
  return (
    <div ref={wrap} className={s.asof}>
      <button type="button" className={cx(s.capsule, s.graphCap)} onClick={() => setOpen(o => !o)} aria-expanded={open} aria-haspopup="dialog"
        aria-label={`Graph: ${label}. Change`} title={info?.source}>
        <span className={s.capLabel}>{label}</span>
        <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true" className={s.caret}><path d="M2 3.5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </button>
      {phone ? (
        <ShellPortal><Sheet open={open} title="Graph" onClose={() => setOpen(false)} cancelLabel="Done"><GraphPicker data={data} onDone={() => setOpen(false)} /></Sheet></ShellPortal>
      ) : open && (
        <div className={cx(s.popover, s.graphPop)} role="dialog" aria-label="Graph"><GraphPicker data={data} onDone={() => setOpen(false)} /></div>
      )}
    </div>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  const { link, graph } = useAppState();
  const path = usePathname();
  const nav = useRef<HTMLElement>(null);
  const isOn = (href: string) => path === href || path === href.slice(0, -1);

  // On phones the nav scrolls sideways; keep the current section in view without moving the page.
  useEffect(() => {
    const el = nav.current;
    const on = el?.querySelector<HTMLElement>("[aria-current='page']");
    if (!el || !on || el.scrollWidth <= el.clientWidth) return;
    const left = on.offsetLeft - el.offsetLeft;
    if (left < el.scrollLeft || left + on.offsetWidth > el.scrollLeft + el.clientWidth) el.scrollLeft = left - 16;
  }, [path]);

  return (
    <div className={s.app}>
      <header className={s.bar}>
        <div className={cx("wrap-app", s.inner)}>
          <Link href="/" className={s.brand} aria-label="Moot home"><Wordmark size={24} /></Link>
          <nav ref={nav} className={s.nav} aria-label="App">
            {NAV.map(([href, label]) => (
              <Link key={href} href={link(href)} className={cx(s.link, isOn(href) && s.on)}
                aria-current={isOn(href) ? "page" : undefined}>{label}</Link>
            ))}
          </nav>
          <div className={s.controls}>
            <GraphMenu />
            <AsOfMenu />
            <ThemeToggle />
          </div>
        </div>
      </header>
      {/* a new graph remounts the page, so every view refetches from it */}
      <main key={graph ?? "default"} className={cx("wrap-app", s.main)}>{children}</main>
    </div>
  );
}
