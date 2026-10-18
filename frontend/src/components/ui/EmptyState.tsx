"use client";
// A calm empty state: a small isometric line drawing of the machine, a sentence-case title, a detail line and an
// optional capsule action, centred.
// Moot says plainly when it has nothing to show; it does not guess.
import type { ReactNode } from "react";
import EmptyStateArt from "./EmptyStateArt";
import s from "./EmptyState.module.css";

export default function EmptyState({ kind, title, detail, action }: { kind: "not_in_graph" | "unknown_entity" | "nothing_selected" | "empty" | "error" | "loading"; title: string; detail?: ReactNode; action?: ReactNode }) {
  const live = kind === "loading" || kind === "error";
  return (
    <div className={`${s.box} ${s[kind]}`} role={live ? "status" : undefined} aria-live={live ? "polite" : undefined}
      aria-busy={kind === "loading" || undefined}>
      <EmptyStateArt kind={kind} />
      <h3 className={`t-title3 ${s.title}`}>{title}</h3>
      {detail && <div className={`t-sub ${s.detail}`}>{detail}</div>}
      {action && <div className={s.action}>{action}</div>}
    </div>
  );
}
