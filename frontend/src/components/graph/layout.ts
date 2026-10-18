// Pure layout: turns the audit rows into positioned parts of the drawing. Every node and cable here comes from a row
// the API returned (the decision, a premise and its path, an evidence edge). Nothing is added for decoration.
import type { Audit, EvidenceEvent, Premise, PremiseState, Rel } from "@/lib/types";
import { decidingEvent } from "@/components/ui";

export type PartKind = "decision" | "premise" | "evidence";

export interface Part {
  key: string;               // unique in the drawing ("D01", "p_gateway_limit", "p_gateway_limit>PR-412")
  id: string;                // the graph id shown to the reader
  kind: PartKind;
  x: number; z: number;      // ground position (world units)
  hop: number;               // 0 for the decision, premise.hops for premises and their evidence
  parent: string | null;     // key of the part this one plugs into
  trail: string[];           // keys from the decision down to this part (the path to highlight)
  state?: PremiseState;
  rel?: Rel;
  deciding?: boolean;        // evidence: the event that decides its premise's state
  premise?: Premise;
  evidence?: EvidenceEvent;
  num?: number;              // callout number (1-based), assigned after filtering
}

export interface Ring { hop: number; r: number; from: number; to: number; label: string }

export interface Drawing {
  parts: Part[];
  rings: Ring[];
  bounds: { minX: number; maxX: number; minZ: number; maxZ: number };
  footprints: { x: number; z: number; e: number }[]; // what the camera must keep in view
}

export const SIZE = {
  plinth: 2.3, plinthH: 0.62, base: 2.9, baseH: 0.16,
  tile: 1.5, tileH: 0.3,
  slabW: 1.05, slabD: 1.35, slabH: 0.1,
  cableW: 0.2, cableH: 0.05,
};

const R1 = 4.6;          // hop-1 ring radius
const RSTEP = 3.6;       // distance between hop rings
const EV_GAP = 3.1;      // evidence ring sits this far outside the deepest premise ring
// The first branch runs to screen-right on a wide stage and straight down on a narrow one, so a chain fills it.
const STARTS = { right: Math.PI / 4, down: -Math.PI / 4 };

/** Lay out the decision, its premises (ring = hop) and their evidence (outer ring) as a sector tree. */
export function layoutAudit(audit: Audit, direction: keyof typeof STARTS = "right"): Drawing {
  const START = STARTS[direction];
  const dKey = audit.decision.id;
  const seen = new Set<string>();
  const premises = [...audit.premises]
    .filter(p => (seen.has(p.id) ? false : (seen.add(p.id), true)))
    .sort((a, b) => a.hops - b.hops || a.id.localeCompare(b.id));
  const byId = new Map(premises.map(p => [p.id, p]));

  // Parent of a premise: the nearest earlier node on its path that is in the drawing.
  const parentOf = (p: Premise): string => {
    for (let i = p.path.length - 2; i >= 1; i--) if (byId.has(p.path[i].id) && p.path[i].id !== p.id) return p.path[i].id;
    return dKey;
  };
  const children = new Map<string, string[]>([[dKey, []]]);
  for (const p of premises) children.set(p.id, []);
  for (const p of premises) children.get(parentOf(p))!.push(p.id);

  const maxHop = premises.reduce((m, p) => Math.max(m, p.hops), 0);
  const ringR = (h: number) => R1 + (h - 1) * RSTEP;
  const rEv = ringR(Math.max(1, maxHop)) + EV_GAP;

  // Leaf weight: each evidence edge and each childless premise takes one slot on the outside.
  const weight = new Map<string, number>();
  const w = (key: string): number => {
    if (weight.has(key)) return weight.get(key)!;
    const kids = children.get(key) ?? [];
    const ev = key === dKey ? 0 : byId.get(key)?.evidence.length ?? 0;
    const v = Math.max(1, kids.reduce((s, k) => s + w(k), 0) + ev);
    weight.set(key, v);
    return v;
  };
  const total = w(dKey);
  // One slot is about 2.5 units of arc on the evidence ring, and never less than a tile on the first ring.
  const unit = Math.max(2.5 / rEv, 2.1 / R1);
  const span = Math.min(Math.PI * 2, total * unit);

  const parts: Part[] = [{
    key: dKey, id: dKey, kind: "decision", x: 0, z: 0, hop: 0, parent: null, trail: [dKey],
  }];
  const place = (key: string, from: number, to: number, trail: string[]) => {
    const kids = children.get(key) ?? [];
    const p = byId.get(key);
    const evs = p ? p.evidence : [];
    const slots = kids.reduce((s, k) => s + w(k), 0) + evs.length;
    const per = slots ? (to - from) / slots : 0;
    let a = from;
    // Evidence on one side, deeper premises on the other, so cables do not cross.
    const deciding = p ? decidingEvent(p.evidence) : null;
    evs.forEach((e, i) => {
      const ang = a + per / 2;
      const ek = `${key}>${e.id}#${i}`;
      parts.push({
        key: ek, id: e.id, kind: "evidence", x: Math.cos(ang) * rEv, z: -Math.sin(ang) * rEv, hop: p!.hops,
        parent: key, trail: [...trail, ek], rel: e.rel, evidence: e, premise: p,
        deciding: !!deciding && deciding.id === e.id && deciding.at === e.at && deciding.rel === e.rel,
      });
      a += per;
    });
    for (const k of kids) {
      const kp = byId.get(k)!;
      const kw = w(k) * per;
      const ang = a + kw / 2;
      const r = ringR(kp.hops);
      parts.push({
        key: k, id: k, kind: "premise", x: Math.cos(ang) * r, z: -Math.sin(ang) * r, hop: kp.hops,
        parent: key, trail: [...trail, k], state: kp.state, premise: kp,
      });
      place(k, a, a + kw, [...trail, k]);
      a += kw;
    }
  };
  place(dKey, START - span / 2, START + span / 2, [dKey]);

  // Hop arcs over the occupied sector, plus the evidence ring.
  const rings: Ring[] = [];
  const pad = Math.min(0.5, (Math.PI * 2 - span) / 2);
  const hops = [...new Set(premises.map(p => p.hops))].sort((a, b) => a - b);
  for (const h of hops) rings.push({ hop: h, r: ringR(h), from: START - span / 2 - pad, to: START + span / 2 + pad, label: `hop ${h}` });
  if (premises.some(p => p.evidence.length)) {
    rings.push({ hop: maxHop + 1, r: rEv, from: START - span / 2 - pad, to: START + span / 2 + pad, label: "evidence" });
  }

  const half = SIZE.base / 2 + 0.4;
  const bounds = { minX: -half, maxX: half, minZ: -half, maxZ: half };
  for (const p of parts) {
    const e = p.kind === "evidence" ? SIZE.slabD / 2 + 0.2 : SIZE.tile / 2 + 0.2;
    bounds.minX = Math.min(bounds.minX, p.x - e); bounds.maxX = Math.max(bounds.maxX, p.x + e);
    bounds.minZ = Math.min(bounds.minZ, p.z - e); bounds.maxZ = Math.max(bounds.maxZ, p.z + e);
  }
  const footprints = parts.map(p => ({ x: p.x, z: p.z, e: p.kind === "decision" ? half : p.kind === "evidence" ? SIZE.slabD / 2 + 0.2 : SIZE.tile / 2 + 0.2 }));
  return { parts, rings, bounds, footprints };
}

/** Parts left after the evidence filter, numbered for callouts in path order (premise, its evidence, deeper premises). */
export function visibleParts(d: Drawing, decidingOnly: boolean): Part[] {
  const keep = d.parts.filter(p => p.kind !== "evidence" || !decidingOnly || p.deciding);
  const root = keep.find(p => p.kind === "decision")!;
  const numbered: Part[] = [];
  const walk = (k: string) => {
    for (const p of keep.filter(p => p.parent === k && p.kind === "premise")) {
      numbered.push(p);
      for (const e of keep.filter(e => e.parent === p.key && e.kind === "evidence")) numbered.push(e);
      walk(p.key);
    }
  };
  walk(root.key);
  return [{ ...root }, ...numbered.map((p, i) => ({ ...p, num: i + 1 }))];
}

export const truncate = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);
