"use client";
// One answer component per tool. Each draws only the rows its tool returned, and reuses the app's own pieces: the
// decision panel, the what-if wiring, the owner ID card, the exhibit cards and the re-open memo with its approval.
import type { ReactNode } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAppState } from "@/lib/appState";
import { longDate, VERDICT_ORDER } from "@/lib/format";
import type {
  AnswerResponse, AnswerTool, Audit, Gate, LedgerAnswer, LedgerRow, Memo, OrphansResponse, OwnerResult, PacketResult, PathNode, Verdict, WhatIfResponse,
} from "@/lib/types";
import { Card, GateBadge, Group, Row, StatCard, StateTag, VERDICT_WORD, VerdictBadge } from "@/components/ui";
import EmptyState from "@/components/ui/EmptyState";
import DecisionPanel from "@/components/decision/DecisionPanel";
import EvidenceExhibits, { collectExhibits } from "@/components/decision/EvidenceExhibits";
import MemoReopen from "@/components/decision/MemoReopen";
import { VerdictWhy } from "@/components/decision/VerdictStamp";
import WhatIfWiring from "@/components/whatif/WhatIfWiring";
import OwnerCard from "@/components/orphans/OwnerCard";
import s from "./ask.module.css";

export interface FollowUp { q: string; tool: AnswerTool; arg: string; key?: "id" | "owner" }

const WORD = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];
const num = (n: number) => (n < WORD.length ? WORD[n] : String(n));
const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);
const lc = (t: string) => t.charAt(0).toLowerCase() + t.slice(1);
export const whyQuestion = (title: string) => `Why do we ${lc(title)}?`;

function Kicker({ children }: { children: ReactNode }) { return <p className={s.kicker}>{children}</p>; }
function Chain({ path, evidence }: { path?: PathNode[]; evidence?: string | null }) {
  if (!path?.length) return null;
  return (
    <span className={s.chain}>
      {path.map((n, i) => <span key={n.id}>{i > 0 && <span className={s.arrow} aria-hidden="true"> → </span>}<span className="id">{n.id}</span></span>)}
      {evidence && <><span className={s.arrow} aria-hidden="true"> ← </span><span className="id">{evidence}</span></>}
    </span>
  );
}
function DecisionRow({ r, after }: { r: { id: string; title: string; systems?: string[]; verdict?: Verdict }; after?: ReactNode }) {
  const { link } = useAppState();
  return (
    <Row href={link("/app/", { d: r.id })} title={r.title}
      subtitle={<><span className="id">{r.id}</span>{r.systems?.length ? ` · ${r.systems.join(", ")}` : ""}</>}
      trailing={after ?? (r.verdict ? <VerdictBadge verdict={r.verdict} /> : undefined)} />
  );
}

function GateAnswer({ g }: { g: Gate }) {
  const id = g.decision_id;
  const say = g.gate === "DENY" ? <>An agent should not act on <span className="id">{id}</span>.</>
    : g.gate === "REVALIDATE" ? <>An agent should check with the owner before acting on <span className="id">{id}</span>.</>
    : <>An agent may act on <span className="id">{id}</span>. Every reason holds, with dated evidence.</>;
  return (
    <Card className={s.card}>
      <Kicker>Agent gate · <span className="id">{id}</span> · {g.title}</Kicker>
      <div className={s.gateRow}><GateBadge gate={g.gate} size="lg" className={s.big} /><p className={s.say}>{say}</p></div>
      {g.reasons.length > 0 && (
        <Group header="Why" onSurface>
          {g.reasons.map((r, i) => <Row key={i} title={r.text} subtitle={<Chain path={r.path} evidence={r.evidence} />} />)}
        </Group>
      )}
      {g.basis.length > 0 && (
        <Group header="What it rests on" onSurface>
          {g.basis.map((b, i) => <Row key={i} title={b.text} subtitle={b.evidence ? <>backed by <span className="id">{b.evidence}</span>{b.at ? ` on ${longDate(b.at)}` : ""}</> : "no dated evidence"} />)}
        </Group>
      )}
      <p className={s.code}><span><b>GET</b> /api/gate/{id}?as_of={g.as_of}</span><span><b>MCP</b> check_action(&quot;{id}&quot;) · read-only, {g.depth} hops deep</span></p>
    </Card>
  );
}

function WhatIfAnswer({ w }: { w: WhatIfResponse }) {
  if (!w.found || !w.premise) return <EmptyState kind="unknown_entity" title="That reason is not in the graph." />;
  const ds = w.decisions ?? [];
  const fall = w.would_fall ?? ds.filter(d => d.flips).length;
  return (
    <Card className={s.card}>
      <Kicker>What if · <span className="id">{w.premise.id}</span></Kicker>
      <h2 className={s.title2}>If “{w.premise.text}” broke today,{" "}
        <span className={s.accent}>{fall ? `${num(fall)} standing ${fall === 1 ? "decision" : "decisions"} would fall.` : "nothing standing would fall."}</span></h2>
      {ds.length > 0 && <WhatIfWiring premise={w.premise} decisions={ds} asOf={w.as_of ?? ""} depth={w.depth ?? 4} />}
      {ds.length > 0 && (
        <Group onSurface label="Decisions resting on it">
          {ds.map(d => <DecisionRow key={d.id} r={d} after={<span className={s.flip}><VerdictBadge verdict={d.before} /><span className={s.arrow} aria-hidden="true">→</span><VerdictBadge verdict={d.after} /></span>} />)}
        </Group>
      )}
      <p className={s.grey}>A read-only path query, {w.depth} hops deep. Nothing is written.{w.systems?.length ? ` Systems touched: ${w.systems.join(", ")}.` : ""}</p>
    </Card>
  );
}

function LeaverAnswer({ group, held }: { group: OrphansResponse["groups"][number]; held?: LedgerRow[] }) {
  const first = group.person.name.split(" ")[0];
  const n = group.decisions.length;
  return (
    <Card className={s.card}>
      <div className={s.idwrap}><OwnerCard group={group} /></div>
      <p className={s.say}><b>{cap(num(n))} {n === 1 ? "decision" : "decisions"} lost {n === 1 ? "its" : "their"} owner</b> when {first} left.
        {group.successor ? <> Moot routes {n === 1 ? "it" : "them"} up the reporting line as it stood that day, to <b>{group.successor.name}</b>.</> : " Nobody on the reporting line is still here."}</p>
      <Group onSurface label={`Decisions ${first} held`}>
        {(held?.length ? held : group.decisions).map(d => <DecisionRow key={d.id} r={d} />)}
      </Group>
    </Card>
  );
}

function OrphansAnswer({ o }: { o: OrphansResponse }) {
  if (!o.groups.length) return <Card className={s.card}><p className={s.say}><b>Nobody who owned a decision has left.</b></p></Card>;
  return <div className={s.stack}>{o.groups.map(g => <LeaverAnswer key={g.person.id} group={g} />)}</div>;
}

function OwnerAnswer({ r }: { r: OwnerResult }) {
  if (!r.owner) return <Card className={s.card}><p className={s.say}><b>{r.decision?.id} has no owner of record.</b></p></Card>;
  if (r.group) return <><Kicker>Owner of record for <span className="id">{r.decision?.id}</span> · {r.decision?.title}</Kicker><LeaverAnswer group={r.group} /></>;
  return (
    <Card className={s.card}>
      <Kicker>Owner of record for <span className="id">{r.decision?.id}</span> · {r.decision?.title}</Kicker>
      <PersonHead name={r.owner.name} role={r.owner.role} />
      <p className={s.say}><b>{r.owner.name} owns {num(r.held.length)} {r.held.length === 1 ? "decision" : "decisions"}</b> and is still here.</p>
      <Group onSurface label="Decisions of record">{r.held.map(d => <DecisionRow key={d.id} r={d} />)}</Group>
    </Card>
  );
}

function PersonHead({ name, role }: { name: string; role?: string | null }) {
  const ini = name.split(/\s+/).map(w => w[0]).join("").slice(0, 2).toUpperCase();
  return (
    <div className={s.person}><span className={s.avatar} aria-hidden="true">{ini}</span>
      <span><span className={s.pname}>{name}</span>{role && <span className={s.prole}>{role}</span>}</span></div>
  );
}

function LedgerAnswerCard({ l, onAsk }: { l: LedgerAnswer; onAsk: (f: FollowUp) => void }) {
  const { link } = useAppState();
  if (l.owner) {
    return (
      <Card className={s.card}>
        <PersonHead name={l.owner.name} />
        <p className={s.say}><b>{l.owner.name} owns {num(l.decisions.length)} {l.decisions.length === 1 ? "decision" : "decisions"}</b>{l.owner.left ? `, and left on ${longDate(l.owner.left)}` : ""}.</p>
        {l.decisions.length > 0 && <Group onSurface label="Decisions of record">{l.decisions.map(d => <DecisionRow key={d.id} r={d} />)}</Group>}
      </Card>
    );
  }
  const all = l.decisions;
  const c = (v: Verdict) => all.filter(r => r.verdict === v).length;
  const groups = VERDICT_ORDER.filter(v => c(v) > 0);
  return (
    <Card className={s.card}>
      <Kicker>Ledger · as of {longDate(l.as_of)}{l.verdict ? ` · ${VERDICT_WORD[l.verdict]} only` : ""}</Kicker>
      {!l.verdict && (
        <>
          <p className={s.say}><b>{cap(num(c("MOOT")))} of {all.length} decisions are moot</b>, {num(c("DISPUTED"))} disputed and {num(c("HOLDS"))} still hold.</p>
          <div className={s.stats}>
            {(["MOOT", "DISPUTED", "HOLDS"] as Verdict[]).map(v => (
              <StatCard key={v} label={VERDICT_WORD[v]} value={c(v)} tone={v === "MOOT" ? "moot" : v === "DISPUTED" ? "disputed" : "holds"}
                onClick={() => onAsk({ q: `Which decisions are ${VERDICT_WORD[v].toLowerCase()}?`, tool: "ledger", arg: v })} />
            ))}
          </div>
        </>
      )}
      {l.verdict && <p className={s.say}><b>{cap(num(all.length))} {all.length === 1 ? "decision is" : "decisions are"} {VERDICT_WORD[l.verdict].toLowerCase()}</b> on {longDate(l.as_of)}.</p>}
      {groups.map(v => (
        <Group key={v} header={`${VERDICT_WORD[v]} · ${c(v)}`} onSurface>
          {all.filter(r => r.verdict === v).map(r => <DecisionRow key={r.id} r={r}
            after={<span className={s.owner}>{r.owner}{r.owner_active === false ? " (left)" : ""}</span>} />)}
        </Group>
      ))}
      <p className={s.grey}><Link href={link("/app/ledger/", l.verdict ? { v: l.verdict } : {})} className="link">
        Open the full ledger{l.verdict ? `, ${VERDICT_WORD[l.verdict].toLowerCase()} only` : ""} <span aria-hidden="true">›</span></Link> for the rot chart, the date and depth controls and every filter.</p>
    </Card>
  );
}

function EvidenceAnswer({ p }: { p: PacketResult }) {
  const { select } = useAppState();
  const a = p.audit;
  const ex = collectExhibits(a.decision.id, a.premises);
  return (
    <Card className={s.card}>
      <Kicker>Evidence · <span className="id">{a.decision.id}</span> · {a.decision.title}</Kicker>
      <div className={s.gateRow}><VerdictBadge verdict={p.verdict} fill size="md" /><GateBadge gate={p.gate} size="md" /></div>
      <VerdictWhy audit={a} onSelect={select} />
      {ex.length ? <EvidenceExhibits exhibits={ex} decisionId={a.decision.id} decidedOn={a.decision.decided_on} asOf={a.as_of} />
        : <p className={s.grey}>No dated evidence either way. Nobody has checked its reasons.</p>}
      {p.caveats?.length > 0 && <p className={s.note}>{p.caveats.join(" ")}</p>}
      <p className={s.grey}><a className="link" href={api.packetUrl(a.decision.id, a.as_of)}>Download the evidence packet as Markdown</a>, for a reviewer.</p>
    </Card>
  );
}

function ReopenAnswer({ m, reload }: { m: Memo & { audit?: Audit }; reload: () => void }) {
  if (!m.found || !m.audit) return <EmptyState kind="not_in_graph" title="That decision is not in the graph." />;
  if (!m.broken?.length) return <Card className={s.card}><p className={s.say}><b>{m.decision.id} has nothing to re-open.</b> No reason under it has expired or been disputed.</p></Card>;
  const to = m.suggested_owner;
  const left = m.owner && !m.owner.active ? m.owner : null;
  const why = left ? `${left.name} left${left.valid_to ? ` on ${longDate(left.valid_to)}` : ""}${to.name && to.name !== left.name ? `; ${to.name.split(" ")[0]} is next up the reporting line` : ""}.` : "";
  return (
    <Card className={s.card}>
      <Kicker>Re-open · <span className="id">{m.decision.id}</span> · {m.decision.title}</Kicker>
      <p className={s.say}><b>Moot drafted a memo to re-open “{m.decision.title}”{to.name ? ` with ${to.name}` : ""}.</b> {why} Nothing is written until you approve.</p>
      <Group header="Which reason broke" onSurface>
        {m.broken.map(b => (
          <Row key={b.premise.id} title={b.premise.text} trailing={<StateTag state={b.state} />}
            subtitle={b.evidence ? <>{b.evidence.rel === "CONTRADICTS" ? "contradicted" : "backed"} {longDate(b.evidence.at)} by <span className="id">{b.evidence.id}</span></> : undefined} />
        ))}
      </Group>
      {m.affected.length > 0 && <Group header="Also resting on it" onSurface>{m.affected.map(a => <DecisionRow key={a.id} r={a} />)}</Group>}
      <details className={s.memo}><summary>Read the memo</summary><pre className={s.cypher}>{m.text}</pre></details>
      <MemoReopen memo={m} audit={m.audit} onChanged={reload} />
    </Card>
  );
}

export function Answer({ res, onAsk, reload }: { res: AnswerResponse; onAsk: (f: FollowUp) => void; reload: () => void }) {
  const r = res.result;
  if (!res.tool || !r) {
    return <EmptyState kind="unknown_entity" title={`Nothing in the graph matches “${res.question.slice(0, 80)}”.`}
      detail="Moot only answers about decisions it has a record of, and it does not guess. Try a rule's name, a reason, or a person." />;
  }
  switch (res.tool) {
    case "audit_decision": return <div className={s.panel}><DecisionPanel id={res.input.decision_id} /></div>;
    case "check_action": return <GateAnswer g={r as Gate} />;
    case "what_if": return <WhatIfAnswer w={r as WhatIfResponse} />;
    case "orphaned_decisions": return <OrphansAnswer o={r as OrphansResponse} />;
    case "decision_owner": return <OwnerAnswer r={r as OwnerResult} />;
    case "ledger": return <LedgerAnswerCard l={r as LedgerAnswer} onAsk={onAsk} />;
    case "evidence_packet": return <EvidenceAnswer p={r as PacketResult} />;
    case "reopen_memo": return <ReopenAnswer m={r as Memo & { audit?: Audit }} reload={reload} />;
  }
}

/** The next questions an answer invites. Each names its tool and input, so it never has to be guessed. */
export function followUps(res: AnswerResponse): FollowUp[] {
  const out: FollowUp[] = [];
  const add = (f: FollowUp) => { if (f.tool !== res.tool || f.arg !== Object.values(res.input)[0]) out.push(f); };
  const r = res.result as Record<string, unknown> | null;
  if (!res.tool || !r) {
    return [{ q: "Which decisions are moot?", tool: "ledger", arg: "MOOT" }, { q: "Why do we cap uploads at 10 MB?", tool: "audit_decision", arg: "D01" },
      { q: "Who left, and what did they own?", tool: "orphaned_decisions", arg: "" }];
  }
  const id = res.input.decision_id;
  if (id) {
    const title = (r.decision as { title?: string } | null)?.title ?? (r as { title?: string }).title ?? ((r.audit as Audit | undefined)?.decision.title);
    const audit = (res.tool === "audit_decision" ? r : r.audit) as Audit | undefined;
    const verdict = (r.verdict as Verdict | undefined) ?? audit?.verdict;
    const gate = res.tool === "check_action" ? (r as unknown as Gate) : null;
    const broken = audit?.premises.find(p => p.state === "expired" || p.state === "disputed")
      ?? (() => { const g = gate?.reasons.find(x => x.premise); return g ? { id: g.premise!, text: g.path?.at(-1)?.title ?? "" } : undefined; })();
    if (title) add({ q: whyQuestion(title), tool: "audit_decision", arg: id });
    add({ q: `Can an agent act on ${id}?`, tool: "check_action", arg: id });
    add({ q: `Show the evidence for ${id}`, tool: "evidence_packet", arg: id });
    if (broken) add({ q: broken.text ? `What if “${broken.text.length > 48 ? broken.text.slice(0, 47) + "…" : broken.text}” broke?` : `What if ${broken.id} broke?`, tool: "what_if", arg: broken.id });
    add({ q: `Who owns ${id}?`, tool: "decision_owner", arg: id });
    if (verdict === "MOOT" || verdict === "DISPUTED") add({ q: `Re-open ${id}`, tool: "reopen_memo", arg: id });
  } else if (res.tool === "what_if") {
    for (const d of ((res.result as WhatIfResponse).decisions ?? []).slice(0, 3)) add({ q: whyQuestion(d.title), tool: "audit_decision", arg: d.id });
  } else if (res.tool === "orphaned_decisions") {
    for (const g of (res.result as OrphansResponse).groups) for (const d of g.decisions.slice(0, 2)) add({ q: `Re-open ${d.id}`, tool: "reopen_memo", arg: d.id });
  } else if (res.tool === "ledger") {
    const l = res.result as LedgerAnswer;
    if (!l.owner) {
      if (l.verdict !== "DISPUTED") add({ q: "Which decisions are disputed?", tool: "ledger", arg: "DISPUTED" });
      add({ q: "Who left, and what did they own?", tool: "orphaned_decisions", arg: "" });
    }
    for (const d of l.decisions.slice(0, 2)) add({ q: whyQuestion(d.title), tool: "audit_decision", arg: d.id });
  }
  return out.slice(0, 5);
}
