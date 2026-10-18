"use client";
// /app/orphans ("Owners"): live decisions whose owner of record has left, one calm card per leaver. Each decision is
// routed up the reporting line (as it stood on the day they left) to the first person still here. A handover is the
// one write, behind an approval sheet, opened by dropping a lanyard badge on the successor or by "Hand to <name>".
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAppState } from "@/lib/appState";
import { longDate, plural } from "@/lib/format";
import type { OrphanDecision, OrphanGroup, OrphansResponse } from "@/lib/types";
import { Group, Row } from "@/components/ui";
import EmptyState from "@/components/ui/EmptyState";
import CypherSpec from "@/components/decision/CypherSpec";
import OwnerCard, { initials } from "./OwnerCard";
import ReportingLine, { firstName, type DropState } from "./ReportingLine";
import OrphanRow from "./OrphanRow";
import HandoverSheet, { type HandoverResult } from "./HandoverSheet";
import s from "./orphans.module.css";

interface Pending { group: OrphanGroup; decision: OrphanDecision }
interface Receipt { decision_id: string; title: string; to: string; from: string; unchanged: boolean }

const WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];
const people = (n: number) => `${WORDS[n] ?? n} ${n === 1 ? "person" : "people"} left.`;

export default function OrphansView() {
  const { asOf, depth, link } = useAppState();
  const { data, error, loading, reload } = useApi<OrphansResponse>(() => api.orphans({ as_of: asOf, depth }), [asOf, depth]);
  const [pending, setPending] = useState<Pending | null>(null);
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const closeSheet = useCallback(() => setPending(null), []);

  if (loading && !data) return <Skeleton />;
  if (error && !data) {
    return (
      <div className={s.view}>
        <EmptyState kind="error" title="Could not load the owners." detail={error}
          action={<button type="button" className="btn ghost small" onClick={reload}>Try again</button>} />
      </div>
    );
  }
  if (!data) return null;

  const date = data.as_of;
  const approve = async (p: Pending): Promise<HandoverResult> => {
    const succ = p.group.successor;
    if (!succ) throw new Error("Nobody in this reporting line is still here.");
    const r = await api.handover({ decision_id: p.decision.id, to: succ.id, as_of: date });
    setReceipts(prev => [{
      decision_id: r.decision_id, title: p.decision.title, to: r.to_name ?? succ.name,
      from: r.valid_from ?? date, unchanged: !!r.unchanged,
    }, ...prev.filter(x => x.decision_id !== r.decision_id)]);
    reload();
    return r;
  };

  return (
    <div className={s.view}>
      <header className={s.head}>
        {data.count ? (
          <>
            <h1 className="t-large">{plural(data.count, "decision")} lost {data.count === 1 ? "its" : "their"} owner.</h1>
            <p>
              <span className="lead-in">{people(data.groups.length)}</span> Each decision goes up the reporting line, as it
              stood on the day they left, to the first person still here.
            </p>
          </>
        ) : (
          <h1 className="t-large">Owners</h1>
        )}
      </header>

      {error && <p className={s.err} role="alert">Could not refresh: {error}</p>}

      {receipts.length > 0 && (
        <Group header="Handed over" label="Handovers you approved">
          {receipts.map(r => (
            <Row key={r.decision_id} href={link("/app/", { d: r.decision_id })} title={r.title}
              subtitle={<><span className="id">{r.decision_id}</span> · {r.unchanged ? `already owned by ${r.to}` : `${r.to} from ${longDate(r.from)}`}</>} />
          ))}
        </Group>
      )}

      {data.groups.length === 0 ? (
        <EmptyState kind="empty" title="Every live decision has an owner who is still here." detail={`As of ${longDate(date)}.`} />
      ) : (
        data.groups.map((g, i) => (
          <LeaverCard
            key={g.person.id}
            group={g}
            asOf={date}
            link={link}
            collapsible={i > 0}
            open={open[g.person.id] ?? i === 0}
            onToggle={v => setOpen(o => ({ ...o, [g.person.id]: v }))}
            pending={pending?.group.person.id === g.person.id ? pending.decision.id : null}
            onAsk={decision => setPending({ group: g, decision })}
          />
        ))
      )}

      {data.queries && data.queries.length > 0 && (
        <details className={s.cypher}>
          <summary>Show the {data.queries.length} read-only queries behind this view</summary>
          <CypherSpec queries={data.queries} />
        </details>
      )}

      {pending && pending.group.successor && (
        <HandoverSheet
          key={`${pending.group.person.id}-${pending.decision.id}`}
          decision={pending.decision}
          from={pending.group.person}
          to={pending.group.successor}
          date={date}
          href={link("/app/", { d: pending.decision.id })}
          onClose={closeSheet}
          onApprove={() => approve(pending)}
        />
      )}
    </div>
  );
}

interface CardProps {
  group: OrphanGroup;
  asOf: string;
  link: (path: string, extra?: Record<string, string>) => string;
  collapsible: boolean;
  open: boolean;
  onToggle: (open: boolean) => void;
  pending: string | null;
  onAsk: (decision: OrphanDecision) => void;
}

function LeaverCard({ group, asOf, link, collapsible, open, onToggle, pending, onAsk }: CardProps) {
  const target = useRef<HTMLDivElement | null>(null);
  const rowBtn = useRef<HTMLButtonElement>(null);
  const hideBtn = useRef<HTMLButtonElement>(null);
  const toggled = useRef(false);
  const [drop, setDrop] = useState<DropState>("idle");
  const [dragging, setDragging] = useState<string | null>(null);
  const getTarget = useCallback(() => target.current, []);
  const { person, successor: succ, decisions } = group;
  const to = succ ? firstName(succ.name) : "";

  // Keep focus on the control that replaced the one just pressed.
  useEffect(() => {
    if (!toggled.current) return;
    toggled.current = false;
    (open ? hideBtn.current : rowBtn.current)?.focus();
  }, [open]);
  const toggle = (v: boolean) => { toggled.current = true; onToggle(v); };

  if (!open) {
    const past = succ ? succ.chain.slice(1, -1).map(n => firstName(n.name)) : [];
    const route = !succ ? "nobody still here to route to" : past.length ? `routes past ${past.join(" and ")} to ${to}` : `routes to ${to}`;
    return (
      <button ref={rowBtn} type="button" className={s.leaverRow} aria-expanded={false} onClick={() => toggle(true)}>
        <span className={s.avatar} aria-hidden="true">{initials(person.name)}</span>
        <span className={s.leaverMain}>
          <span className={s.leaverName}>{person.name}</span>
          <span className={s.leaverSub}>
            {person.left ? `Left ${longDate(person.left)} · ` : ""}{plural(decisions.length, "decision")} · {route}
          </span>
        </span>
        <span className={s.chev} aria-hidden="true">›</span>
      </button>
    );
  }

  return (
    <section className={s.card} aria-labelledby={`leaver-${person.id}`}>
      {collapsible && (
        <button ref={hideBtn} type="button" className={`btn plain small ${s.hide}`} aria-expanded onClick={() => toggle(false)}>
          Hide
        </button>
      )}
      <OwnerCard group={group} />
      <div className={s.cardMain}>
        <ReportingLine group={group} asOf={asOf} dropRef={target} drop={drop} dragging={dragging} />
        <div className={s.held}>
          <h3 id={`held-${person.id}`}>Decisions held by {person.name}</h3>
          <ol className={s.rows} aria-labelledby={`held-${person.id}`}>
            {decisions.map(d => (
              <OrphanRow
                key={d.id}
                d={d}
                href={link("/app/", { d: d.id })}
                successor={succ ? { id: succ.id, name: succ.name } : null}
                confirming={pending === d.id}
                getTarget={getTarget}
                onDragState={st => { setDrop(st); setDragging(st === "idle" ? null : d.id); }}
                onAsk={() => onAsk(d)}
              />
            ))}
          </ol>
        </div>
        {succ && (
          <p className={s.foot}>
            Drag a badge onto {to} to hand the decision over, or tap Hand to {to}. Nothing is written until you approve.
          </p>
        )}
      </div>
    </section>
  );
}

function Skeleton() {
  return (
    <div className={s.view} aria-busy="true" aria-label="Walking the reporting lines">
      <div className={s.head}>
        <div className="skeleton" style={{ width: "min(460px, 100%)", height: 38 }} />
        <div className="skeleton" style={{ width: "min(680px, 100%)", height: 22 }} />
      </div>
      <div className={s.card}>
        <div className="skeleton" style={{ flex: "0 0 280px", maxWidth: "100%", height: 400, borderRadius: 18 }} />
        <div className={s.cardMain}>
          <div className="skeleton" style={{ width: "min(420px, 100%)", height: 64 }} />
          <div className="skeleton" style={{ height: 96 }} />
          <div className="skeleton" style={{ height: 96 }} />
        </div>
      </div>
    </div>
  );
}
