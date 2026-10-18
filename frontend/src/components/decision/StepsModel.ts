// Turn one audit's rows into a step-by-step walkthrough and the nodes of its figure. Pure: rows in, steps out.
import type { Audit, EvidenceEvent, Premise } from "@/lib/types";
import { STATE_WORD, VERDICT_WORD, decidingEvent } from "@/components/ui";
import { longDate } from "@/lib/format";

export type Tone = "accent" | "holds" | "disputed" | "muted" | null;

export interface FigNode {
  key: string;
  kind: "decision" | "premise" | "evidence" | "superseded";
  level: number;            // indent in the figure
  parent: string | null;
  id: string;
  title: string;
  tag: string;              // small note in sentence case: premise state, or relation and date
  tone: Tone;
  step: number;             // the step that reveals it
  tagStep: number;          // the step from which its tag is known
}

export interface Step { short: string; title: string; sentences: string[]; adds: string[] }

export interface StepsModel { nodes: FigNode[]; steps: Step[] }

const q = (t: string) => `“${t}”`;
const L = longDate;
const V = (v: Audit["verdict"]) => VERDICT_WORD[v].toLowerCase();
const byDate = (a: EvidenceEvent, b: EvidenceEvent) =>
  a.at.localeCompare(b.at) || (a.stated ?? a.at).localeCompare(b.stated ?? b.at) || Number(a.rel === "SUPPORTS") - Number(b.rel === "SUPPORTS");
const pkey = (p: { id: string; hops: number }) => `${p.id}@${p.hops}`;
const evKey = (p: Premise, i: number) => `${pkey(p)}:e${i}`;

function stateTone(s: Premise["state"]): Tone {
  return s === "expired" ? "accent" : s === "disputed" ? "disputed" : s === "holds" ? "holds" : "muted";
}

function eventSentence(e: EvidenceEvent, text: string): string {
  const when = `on ${L(e.at)}${e.stated && e.stated !== e.at ? `, recorded ${L(e.stated)}` : ""}`;
  if (e.ruling) {
    const by = e.author ? ` by ${e.author}` : "";
    return `${e.id}, an owner's ruling${by}, ${e.rel === "SUPPORTS" ? "re-affirmed" : "rejected"} ${q(text)} ${when}.`;
  }
  return `${e.id}${e.author ? ` (${e.author})` : ""} ${e.rel === "CONTRADICTS" ? "contradicted" : "supported"} ${q(text)} ${when}.`;
}

export function buildSteps(audit: Audit): StepsModel {
  const d = audit.decision;
  const nodes: FigNode[] = [];
  const steps: Step[] = [];

  // 00 the decision
  const owner = audit.owner;
  const ownerLine = owner
    ? owner.active
      ? `${owner.name}${owner.role ? ` (${owner.role})` : ""} owns it.`
      : `${owner.name}${owner.role ? ` (${owner.role})` : ""} owned it and left on ${L(owner.valid_to)}.`
    : "No owner is on record as of this date.";
  nodes.push({ key: "dec", kind: "decision", level: 0, parent: null, id: d.id, title: d.title, tag: `Decided ${L(d.decided_on)}`, tone: null, step: 0, tagStep: 0 });
  steps.push({
    short: "Decision", title: "Start with the decision",
    sentences: [
      `${d.id}, ${q(d.title)}, was decided on ${L(d.decided_on)}.`,
      ownerLine,
      `Moot reads the graph as of ${L(audit.as_of)} and follows its reasons up to ${audit.depth} ${audit.depth === 1 ? "hop" : "hops"} down.`,
    ],
    adds: ["dec"],
  });

  if (audit.verdict === "NOT_YET") {
    steps.push({
      short: "Verdict", title: "Not decided yet",
      sentences: [`As of ${L(audit.as_of)} this decision had not been made; it was decided on ${L(d.decided_on)}.`, "There is nothing to audit before that date."],
      adds: [],
    });
    return { nodes, steps };
  }

  if (audit.verdict === "RETIRED") {
    const sup = audit.superseded_by;
    if (sup) {
      const edge = sup.kind === "decision" ? "Supersedes it" : "Retires it";
      nodes.push({ key: "sup", kind: "superseded", level: 1, parent: "dec", id: sup.id, title: sup.title, tag: `${edge} · ${L(sup.at)}`, tone: "muted", step: 1, tagStep: 1 });
      steps.push({
        short: "Retired", title: "Something replaced it",
        sentences: [
          `${sup.id}, ${q(sup.title)}, ${sup.kind === "decision" ? "superseded" : "retired"} it on ${L(sup.at)}.`,
          ...(sup.quote ? [`It says: ${q(sup.quote)}`] : []),
        ],
        adds: ["sup"],
      });
    }
    steps.push({
      short: "Verdict", title: "The verdict",
      sentences: [
        sup ? `It has been retired since ${L(sup.at)}.` : "It has been retired.",
        "A retired decision is not audited as if it were still in force; its reasons no longer bear on any action.",
      ],
      adds: [],
    });
    return { nodes, steps };
  }

  const premises = audit.premises;
  if (!premises.length) {
    steps.push({
      short: "Verdict", title: "No reason recorded",
      sentences: [`Nobody wrote down why ${d.id} was made, so there is nothing to check it against.`, "So the verdict is undocumented."],
      adds: [],
    });
    return { nodes, steps };
  }

  // 01..: one step per hop. A premise hangs under the premise one hop above it on its own path.
  const maxHop = Math.max(...premises.map(p => p.hops));
  const known = new Set(premises.map(pkey));
  const parentOf = (p: Premise) => {
    if (p.hops <= 1 || p.path.length < 2) return "dec";
    const k = `${p.path[p.path.length - 2].id}@${p.hops - 1}`;
    return known.has(k) ? k : "dec";
  };
  const evidenceStep = maxHop + 1;
  const textOf = new Map(premises.map(p => [p.id, p.text]));

  for (let h = 1; h <= maxHop; h++) {
    const at = premises.filter(p => p.hops === h);
    const sentences = at.map(p => {
      const parent = p.path[p.path.length - 2];
      return h === 1
        ? `${d.id} rests on ${q(p.text)}${p.kind ? ` (a ${p.kind})` : ""}.`
        : `${q(textOf.get(parent?.id) ?? parent?.title ?? "")} rests on ${q(p.text)}.`;
    });
    if (h === maxHop && h === audit.depth) sentences.push(`Depth ${audit.depth} stops here; anything deeper is not read.`);
    steps.push({
      short: h === 1 ? "Reasons" : `Hop ${h}`,
      title: h === 1 ? `The stated ${at.length === 1 ? "reason" : "reasons"}` : `What those rest on, hop ${h}`,
      sentences, adds: at.map(pkey),
    });
  }

  // Tree order for the figure: depth-first from the decision, each premise followed by its dated evidence.
  const children = new Map<string, Premise[]>();
  for (const p of premises) {
    const k = parentOf(p);
    children.set(k, [...(children.get(k) ?? []), p]);
  }
  const evAdds: string[] = [];
  const walk = (k: string) => {
    for (const p of children.get(k) ?? []) {
      const key = pkey(p);
      if (nodes.some(n => n.key === key)) continue;
      nodes.push({ key, kind: "premise", level: p.hops, parent: k, id: p.id, title: p.text, tag: STATE_WORD[p.state], tone: stateTone(p.state), step: p.hops, tagStep: evidenceStep });
      [...p.evidence].sort(byDate).forEach((e, i) => {
        const tag = `${e.ruling ? "Ruling, " : ""}${e.rel === "CONTRADICTS" ? (e.ruling ? "contradicts" : "Contradicts") : (e.ruling ? "supports" : "Supports")} · ${L(e.at)}`;
        nodes.push({ key: evKey(p, i), kind: "evidence", level: p.hops + 1, parent: key, id: e.id, title: e.title, tag,
          tone: e.rel === "CONTRADICTS" ? "accent" : "holds", step: evidenceStep, tagStep: evidenceStep });
        evAdds.push(evKey(p, i));
      });
      walk(key);
    }
  };
  walk("dec");

  // The dated evidence, oldest first, then the reasons nobody checked.
  const events = premises.flatMap(p => p.evidence.map(e => ({ p, e }))).sort((a, b) => byDate(a.e, b.e));
  const evSentences = events.map(({ p, e }) => eventSentence(e, p.text));
  for (const p of premises) {
    if (p.state === "unchecked") evSentences.push(`${q(p.text)} could not be checked: ${p.unchecked ?? "no answer"}.`);
    else if (p.state === "unevidenced") evSentences.push(`Nothing on record either way for ${q(p.text)}; nobody has checked it.`);
  }
  steps.push({
    short: "Evidence", title: events.length ? "The dated evidence" : "No dated evidence",
    sentences: events.length ? evSentences : [`No evidence on any reason is dated on or before ${L(audit.as_of)}.`, ...evSentences],
    adds: evAdds,
  });

  // Last: the verdict and the premise state that decided it.
  const keyOfEvent = (p: Premise, e: EvidenceEvent | null) => {
    if (!e) return null;
    const i = [...p.evidence].sort(byDate).indexOf(e);
    return i >= 0 ? evKey(p, i) : null;
  };
  const why: string[] = [];
  const adds: string[] = [];
  const expired = premises.filter(p => p.state === "expired");
  const disputed = premises.filter(p => p.state === "disputed");
  const loose = premises.filter(p => p.state === "unevidenced" || p.state === "unchecked");
  if (audit.verdict === "MOOT" && expired.length) {
    for (const p of expired) {
      const c = decidingEvent(p.evidence);
      why.push(`${q(p.text)} is expired: ${c ? `${c.id} contradicted it on ${L(c.at)} and nothing re-affirmed it after.` : "its latest evidence contradicts it."}`);
      if (p.hops > 1 && p.path[1]) why.push(`It sits ${p.hops} hops down, under ${q(p.path[1].title)}, so the break reaches ${d.id} through that reason.`);
      if (p.contradicted_before_decision) why.push("It was already contradicted before the decision was made.");
      adds.push(pkey(p));
      const k = keyOfEvent(p, c);
      if (k) adds.push(k);
    }
    why.push(`One expired reason is enough, so the verdict is moot as of ${L(audit.as_of)}.`);
  } else if (audit.verdict === "DISPUTED" && disputed.length) {
    for (const p of disputed) {
      const ev = [...p.evidence].sort(byDate);
      const c = ev.filter(e => e.rel === "CONTRADICTS").pop();
      const s = ev.filter(e => e.rel === "SUPPORTS").pop();
      why.push(c && s && s.at >= c.at
        ? `${q(p.text)} was contradicted by ${c.id} on ${L(c.at)} and re-affirmed by ${s.id} on ${L(s.at)}.`
        : c ? `${q(p.text)} was flagged by ${c.id} on ${L(c.at)}, a licence or vulnerability check that no stated reason depends on, so it is disputed, not dead.`
        : `${q(p.text)} has evidence on both sides.`);
      adds.push(pkey(p));
      for (const e of [c, s]) { const k = e ? keyOfEvent(p, e) : null; if (k) adds.push(k); }
    }
    why.push("Nothing is expired, but the record disagrees with itself, so the verdict is disputed until the owner rules.");
  } else if (audit.verdict === "HOLDS") {
    for (const p of premises.filter(x => x.state === "holds")) {
      adds.push(pkey(p));
      const s = [...p.evidence].sort(byDate).filter(e => e.rel === "SUPPORTS").pop() ?? null;
      const k = keyOfEvent(p, s);
      if (k) adds.push(k);
    }
    why.push(`Every reason with evidence is supported, and nothing contradicts any reason as of ${L(audit.as_of)}, so the verdict holds.`);
  } else {
    why.push(`So the verdict is ${V(audit.verdict)}.`);
  }
  if (loose.length && audit.verdict !== "MOOT") {
    why.push(`${loose.length === 1 ? "One reason has" : `${loose.length} reasons have`} no dated evidence either way; that does not change the verdict, but nobody has checked ${loose.length === 1 ? "it" : "them"}.`);
  }
  steps.push({ short: "Verdict", title: "The verdict and why", sentences: why, adds });

  return { nodes, steps };
}
