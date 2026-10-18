"use client";
// A numbered exhibit card. Front: the document (title, id, kind, date, author), a dithered band that places it between
// the decision date and the as-of date, and its relation pill. Back: the quote, the dates and the reason it bears on,
// with Trace (which decisions this document reaches) and Read source; both open in a sheet.
import { useCallback, useEffect, useRef, useState, type PointerEvent } from "react";
import { Group, Pill, Row, Sheet, StateTag, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { useAppState } from "@/lib/appState";
import { longDate, plural } from "@/lib/format";
import type { DocumentResponse, EvidenceEvent, Premise, TraceResponse } from "@/lib/types";
import EvidenceDither, { datePosition } from "./EvidenceDither";
import { exhibitLabel } from "./PremiseBlock";
import s from "./Evidence.module.css";

type Load<T> = { phase: "idle" } | { phase: "loading" } | { phase: "ok"; data: T } | { phase: "error"; message: string };
const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

const KIND_WORD: Record<string, string> = {
  pr: "Pull request", adr: "Decision record", ticket: "Ticket", chat: "Chat", doc: "Document", incident: "Incident",
  postmortem: "Postmortem", check: "Check", email: "Email", meeting: "Meeting notes", commit: "Commit", release: "Release",
};
export const kindWord = (k: string) => KIND_WORD[k] ?? (k ? k.charAt(0).toUpperCase() + k.slice(1) : "Document");

export default function EvidenceCard({ n, ev, premise, anchor, decisionId, decidedOn, asOf }: {
  n: number; ev: EvidenceEvent; premise: Premise; anchor: string; decisionId: string; decidedOn: string; asOf: string;
}) {
  const { select } = useAppState();
  const [flipped, setFlipped] = useState(false);
  const [trace, setTrace] = useState<Load<TraceResponse>>({ phase: "idle" });
  const [doc, setDoc] = useState<Load<DocumentResponse>>({ phase: "idle" });
  const [sheet, setSheet] = useState<"trace" | "source" | null>(null);
  const tiltRef = useRef<HTMLDivElement>(null);
  const frontRef = useRef<HTMLButtonElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  const turned = useRef(false);
  const num = exhibitLabel(n);
  const contra = ev.rel === "CONTRADICTS";
  const relWord = contra ? "Contradicts" : "Supports";
  // Owner rulings are Findings, not documents: there is no source text or trace for them.
  const readable = !ev.ruling;
  const closeSheet = useCallback(() => setSheet(null), []);

  useEffect(() => {
    if (!turned.current) return;
    (flipped ? backRef : frontRef).current?.focus({ preventScroll: true });
  }, [flipped]);

  const turn = () => { turned.current = true; setFlipped(f => !f); };

  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    const el = tiltRef.current;
    if (!el || e.pointerType !== "mouse" || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const r = el.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
    el.style.setProperty("--ry", `${((x - 0.5) * 8).toFixed(2)}deg`);
    el.style.setProperty("--rx", `${((0.5 - y) * 6).toFixed(2)}deg`);
    el.style.setProperty("--mx", `${(x * 100).toFixed(1)}%`);
    el.style.setProperty("--my", `${(y * 100).toFixed(1)}%`);
    el.dataset.tilt = "on";
  };
  const onLeave = () => {
    const el = tiltRef.current;
    if (!el) return;
    for (const k of ["--rx", "--ry", "--mx", "--my"]) el.style.removeProperty(k);
    delete el.dataset.tilt;
  };

  const runTrace = () => {
    setSheet("trace");
    if (trace.phase === "ok" || trace.phase === "loading") return;
    setTrace({ phase: "loading" });
    api.trace(ev.id).then(data => setTrace({ phase: "ok", data }), e => setTrace({ phase: "error", message: message(e) }));
  };
  const readSource = () => {
    setSheet("source");
    if (doc.phase === "ok" || doc.phase === "loading") return;
    setDoc({ phase: "loading" });
    api.document(ev.id).then(data => setDoc({ phase: "ok", data }), e => setDoc({ phase: "error", message: message(e) }));
  };

  const pill = <Pill tone={contra ? "moot" : "holds"}>{ev.ruling ? `Ruling · ${relWord.toLowerCase()}` : relWord}</Pill>;

  return (
    <li className={s.cell} id={anchor}>
      <div className={s.stage}>
      <div ref={tiltRef} className={s.tilt} onPointerMove={onMove} onPointerLeave={onLeave}>
        <div className={cx(s.card, flipped && s.flipped)}>
          <button ref={frontRef} type="button" className={cx(s.face, s.front)} aria-pressed={flipped}
            inert={flipped} onClick={turn}
            aria-label={`Exhibit ${num}: ${ev.title}. ${relWord}, ${longDate(ev.at)}. Turn over to read the quote.`}>
            <span className={s.head}>
              <span className={s.eyebrow}>Exhibit {num}</span>
              <span className={s.num} aria-hidden="true">{num}</span>
            </span>
            <span className={s.title}>{ev.title}</span>
            <span className={s.facts}>
              <span className="id">{ev.id}</span>
              <span>{kindWord(ev.kind)}</span>
              <span>{longDate(ev.date || ev.at)}</span>
              {ev.author && <span>{ev.author}</span>}
            </span>
            <span className={s.band}>
              <EvidenceDither className={cx(s.dither, contra && s.ditherContra)} seed={ev.id} position={datePosition(ev.at, decidedOn, asOf)} />
              <span className={s.bandScale}><span>Decided {longDate(decidedOn)}</span><span>As of {longDate(asOf)}</span></span>
            </span>
            <span className={s.foot}>{pill}<span className={s.turnHint}>Turn over</span></span>
            <span className={s.sheen} aria-hidden="true" />
          </button>

          <div className={cx(s.face, s.back)} inert={!flipped}>
            <div className={s.head}>
              <span className={s.eyebrow}>Exhibit {num} · <span className="id">{ev.id}</span></span>
              {pill}
            </div>
            {ev.quote ? <blockquote className={s.quote}>“{ev.quote}”</blockquote> : <p className={s.muted}>No quote recorded on this edge.</p>}
            <dl className={s.dl}>
              <div><dt>Dated</dt><dd>{longDate(ev.at)}</dd></div>
              {ev.stated && ev.stated !== ev.at && <div><dt>Stated</dt><dd>{longDate(ev.stated)}</dd></div>}
              {ev.author && <div><dt>By</dt><dd>{ev.author}</dd></div>}
              <div><dt>Bears on</dt><dd><span className={s.bears}>{premise.text}</span> <StateTag state={premise.state} /></dd></div>
            </dl>

            <div className={s.actions}>
              {readable && <button type="button" className="btn ghost small" onClick={runTrace}>Trace</button>}
              {readable && <button type="button" className="btn ghost small" onClick={readSource}>Read source</button>}
              <button ref={backRef} type="button" className={cx("btn plain small", s.turnBack)} aria-pressed={flipped} onClick={turn}
                aria-label={`Turn exhibit ${num} face up`}>Turn back</button>
            </div>
            {!readable && <p className={s.muted}>Recorded by an owner ruling in Moot. There is no source document.</p>}
          </div>
        </div>
      </div>
      </div>

      <Sheet open={sheet === "trace"} title={`Trace ${ev.id}`} onClose={closeSheet}>
        {trace.phase === "loading" && <Skeleton label="Tracing" />}
        {trace.phase === "error" && <p className={s.error} role="alert">{trace.message}</p>}
        {trace.phase === "ok" && (
          <>
            <p className={s.sheetLead}>
              <span className="lead-in">{ev.id} reaches {plural(trace.data.reaches.length, "decision")}.</span>{" "}
              {trace.data.evidence.title}
            </p>
            <Group header="Decisions it reaches">
              {trace.data.reaches.map(r => r.id === decisionId ? (
                <Row key={r.id} title={r.title} subtitle={<><span className="id">{r.id}</span> · this decision · {plural(r.hops, "hop")}</>} />
              ) : (
                <Row key={r.id} title={r.title} subtitle={<><span className="id">{r.id}</span> · {plural(r.hops, "hop")}</>}
                  onClick={() => { closeSheet(); select(r.id); }} ariaLabel={`Open ${r.id}: ${r.title}`} />
              ))}
            </Group>
          </>
        )}
      </Sheet>

      <Sheet open={sheet === "source"} title={ev.id} onClose={closeSheet}>
        {doc.phase === "loading" && <Skeleton label="Loading source" />}
        {doc.phase === "error" && <p className={s.error} role="alert">{doc.message}</p>}
        {doc.phase === "ok" && (
          <>
            <p className={s.sheetLead}>
              <span className="lead-in">{doc.data.title}.</span>{" "}
              {[kindWord(doc.data.kind), doc.data.date && longDate(doc.data.date), doc.data.author].filter(Boolean).join(" · ")}
            </p>
            <pre className={s.source} tabIndex={0} aria-label={`Source text of ${doc.data.id}`}>{doc.data.text}</pre>
            {doc.data.path && <p className={`t-footnote ${s.path}`}>{doc.data.path}</p>}
          </>
        )}
      </Sheet>
    </li>
  );
}

function Skeleton({ label }: { label: string }) {
  return <div className={s.loading} aria-busy="true" aria-label={label}><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></div>;
}
