"use client";
// The owner of record as an ID card: handle, initials portrait, role, who they reported to, name with a LEFT stamp,
// decisions held and where they route. Calm labels (sentence case); the handle is the only mono.
import { useEffect, useRef } from "react";
import type { OrphanGroup } from "@/lib/types";
import { longDate, plural } from "@/lib/format";
import s from "./orphans.module.css";

export const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join("").toUpperCase();

export default function OwnerCard({ group }: { group: OrphanGroup }) {
  const { person, successor, decisions } = group;
  const card = useRef<HTMLElement>(null);

  // A small tilt toward the pointer, so the card reads as an object. Off for reduced motion and touch.
  useEffect(() => {
    const el = card.current;
    if (!el) return;
    const mq = matchMedia("(prefers-reduced-motion: reduce)");
    const move = (e: PointerEvent) => {
      if (mq.matches || e.pointerType !== "mouse") return;
      const r = el.getBoundingClientRect();
      const dx = (e.clientX - r.left) / r.width - 0.5, dy = (e.clientY - r.top) / r.height - 0.5;
      el.style.transform = `perspective(900px) rotateX(${(-dy * 6).toFixed(2)}deg) rotateY(${(dx * 8).toFixed(2)}deg)`;
    };
    const leave = () => { el.style.transform = ""; };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerleave", leave);
    return () => { el.removeEventListener("pointermove", move); el.removeEventListener("pointerleave", leave); };
  }, []);

  const reportedTo = successor && successor.chain.length > 1 ? successor.chain[1].name : "Not recorded";
  const left = longDate(person.left);

  return (
    <article ref={card} className={s.idcard} aria-label={`ID card: ${person.name}, ${person.role}${left ? `, left ${left}` : ""}`}>
      <span className={s.idslot} aria-hidden="true" />
      <header className={s.idhead}>
        <span>Owner of record</span>
        <span className="id">{person.id}</span>
      </header>
      <div className={s.idbody}>
        <div className={s.portrait} aria-hidden="true"><span>{initials(person.name)}</span></div>
        <dl className={s.idfields}>
          <div className={s.field}><dt>Role</dt><dd>{person.role}</dd></div>
          <div className={s.field}><dt>Reported to</dt><dd>{reportedTo}</dd></div>
        </dl>
      </div>
      <div className={s.idname}>
        <span className={s.fieldLabel}>Name</span>
        <h2 id={`leaver-${person.id}`}>{person.name}</h2>
        {left && (
          <div className={s.stamp} aria-hidden="true">
            <b>LEFT</b><span>{left}</span>
          </div>
        )}
      </div>
      <dl className={s.idgrid}>
        <div className={s.field}><dt>Decisions held</dt><dd className="tabular">{decisions.length}</dd></div>
        <div className={s.field}><dt>Routes to</dt><dd>{successor ? successor.name : "Nobody still here"}</dd></div>
      </dl>
      <footer className={s.idfoot}>
        {plural(decisions.length, "decision")} without an owner{left && <> since <span className={s.nowrap}>{left}</span></>}.
      </footer>
    </article>
  );
}
