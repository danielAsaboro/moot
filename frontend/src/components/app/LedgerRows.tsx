"use client";
// The ledger itself: one inset grouped list per verdict (Moot first), rows = title and "owner · system". Long groups
// show the first six until expanded. Click or Enter opens a decision; Up/Down move between rows with one tab stop.
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Group, Row, VERDICT_WORD, cx } from "@/components/ui";
import { VERDICT_ORDER } from "@/lib/format";
import type { LedgerRow, Verdict } from "@/lib/types";
import s from "./ledger.module.css";

const FIRST = 6;

export function LedgerSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className={s.groups} aria-hidden>
      <div className={s.skGroup}>
        <span className={cx("skeleton", s.skHead)} />
        <div className={s.skBody}>
          {Array.from({ length: rows }, (_, i) => (
            <div key={i} className={s.skRow}>
              <span className={cx("skeleton", s.skTitle)} style={{ width: `${78 - (i % 3) * 14}%` }} />
              <span className={cx("skeleton", s.skMeta)} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const subtitle = (d: LedgerRow) => {
  const who = d.owner ? `${d.owner}${d.owner_active ? "" : " (left)"}` : "No owner";
  return d.systems.length ? `${who} · ${d.systems.join(", ")}` : who;
};

export default function LedgerRows({ rows, selected, onOpen }: { rows: LedgerRow[]; selected: string | null; onOpen: (id: string) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState<Set<Verdict>>(new Set());
  const [focusId, setFocusId] = useState<string | null>(null);
  const pendingFocus = useRef<string | null>(null);

  const groups = useMemo(() => {
    const by = new Map<Verdict, LedgerRow[]>();
    for (const d of rows) by.set(d.verdict, [...(by.get(d.verdict) ?? []), d]);
    const order = [...VERDICT_ORDER, ...[...by.keys()].filter(v => !VERDICT_ORDER.includes(v))];
    return order.filter(v => by.has(v)).map(v => {
      const all = by.get(v)!;
      const selIdx = all.findIndex(d => d.id === selected);
      const open = expanded.has(v) || all.length <= FIRST + 1 || selIdx >= FIRST;
      return { v, all, shown: open ? all : all.slice(0, FIRST), more: open ? 0 : all.length - FIRST };
    });
  }, [rows, expanded, selected]);
  const visible = useMemo(() => groups.flatMap(g => g.shown), [groups]);

  // Rows come from the shared <Row>, so the list keeps one tab stop by setting tabIndex on the rendered buttons:
  // the focused row, else the selected one, else the first.
  const buttons = () => Array.from(box.current?.querySelectorAll<HTMLButtonElement>("button[aria-pressed]") ?? []);
  const selIdx = visible.findIndex(d => d.id === selected);
  const focusIdx = visible.findIndex(d => d.id === focusId);
  const tab = focusIdx >= 0 ? focusIdx : selIdx >= 0 ? selIdx : 0;
  useLayoutEffect(() => {
    const list = buttons();
    list.forEach((b, i) => { b.tabIndex = i === tab ? 0 : -1; });
    // "Show all" disappears when pressed; focus moves to the first row it revealed.
    if (pendingFocus.current) {
      const i = visible.findIndex(d => d.id === pendingFocus.current);
      pendingFocus.current = null;
      if (i >= 0) list[i]?.focus();
    }
  });

  // A selection made elsewhere (the ask field, a link) brings its row into view without moving focus. Only in the
  // two-column layout; on a phone the ledger is not on screen while a decision is open.
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) { mounted.current = true; return; }
    if (selIdx >= 0 && window.matchMedia("(min-width: 961px)").matches) buttons()[selIdx]?.scrollIntoView({ block: "nearest" });
  }, [selIdx]);

  const onKey = (e: KeyboardEvent) => {
    const list = buttons();
    const i = list.indexOf(e.target as HTMLButtonElement);
    if (i < 0) return;
    const to = e.key === "ArrowDown" ? i + 1 : e.key === "ArrowUp" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? list.length - 1 : null;
    if (to === null) return;
    e.preventDefault();
    list[Math.max(0, Math.min(list.length - 1, to))]?.focus();
  };
  const onFocus = (e: React.FocusEvent) => {
    const i = buttons().indexOf(e.target as HTMLButtonElement);
    if (i >= 0) setFocusId(visible[i]?.id ?? null);
  };

  return (
    <div ref={box} className={s.groups} onKeyDown={onKey} onFocus={onFocus}>
      {groups.map(g => (
        <Group key={g.v} label={`${VERDICT_WORD[g.v]}, ${g.all.length}`}
          header={<span>{VERDICT_WORD[g.v]} · {g.all.length}</span>}>
          {g.shown.map(d => (
            <Row key={d.id} title={d.title} subtitle={subtitle(d)} clip selected={d.id === selected} onClick={() => onOpen(d.id)} />
          ))}
          {g.more > 0 && (
            <button type="button" className={s.more} onClick={() => { pendingFocus.current = g.all[FIRST].id; setExpanded(x => new Set(x).add(g.v)); }}>
              Show all {g.all.length}
            </button>
          )}
        </Group>
      ))}
    </div>
  );
}
