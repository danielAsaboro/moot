// The transit map: every reason is a line, every decision a station on the line it rests on, every piece of dated
// evidence an inspection (supports) or a break (contradicts) along that line. A reason that expires closes its line,
// and the stations on it stay on the map: the rules are still enforced, their reason no longer runs.
// Plain SVG plus an HTML label layer; the layout is deterministic, so nothing moves when the month changes.
// Read-only: every mark is a row from GET /api/map, and "What if it broke?" asks GET /api/whatif.
import type { MapData, PremiseState, Verdict, WhatIfResponse } from "@/lib/types";

export interface MetroOptions {
  /** href for another /app page that keeps as_of and depth */
  href: (path: string, extra?: Record<string, string>) => string;
  navigate: (href: string) => void;
  whatIf: (premiseId: string, asOf: string) => Promise<WhatIfResponse>;
  /** a decision to open on load */
  initial?: string | null;
}

type V = Verdict | null;
type S = PremiseState | null;
type Pt = [number, number];
interface Ev { id: string; rel: string; at: string; quote?: string; p: string }
interface Target { kind: "st" | "line" | "ev"; id: string; p?: string; ev?: string }
interface Line { id: string; pts: Pt[]; w: number; y: number; runStart: number; isRoot: boolean; knot: Pt | null }
interface Station { id: string; x: number; y: number; r: number; mode: string; lone?: boolean }
interface Mark { ev: Ev; p: string; x: number; y: number; w: number }
interface Box { kind: "st" | "ln" | "ev" | "status" | "xfer"; id: string; p?: string; x: number; y: number; w: number; h: number; rel?: string; at?: string; text?: string }
interface Xfer { a: Pt; b: Pt; src: string; dst: string; at: string }
interface Lay { lines: Record<string, Line>; stations: Record<string, Station>; marks: Mark[]; labels: Box[]; xfers: Xfer[] }
interface DistBox { name: string[]; net: boolean; sub: string; x: number; y: number; w: number; h: number }
interface District { kind: "net" | "sys"; name: string; root?: string; ds: string[]; ps: string[]; items: { d: string; p: string | null }[] }
interface Preview { p: string; flips: Set<string>; would: number; already: number }

const MN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const esc = (s: unknown) => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
const fmtD = (s?: string | null) => { if (!s) return ""; const [y, m, d] = s.split("-").map(Number); return `${d} ${MN[m - 1].slice(0, 3)} ${y}`; };
const fmtLong = (s: string) => { const [y, m, d] = s.split("-").map(Number); return `${d} ${MN[m - 1]} ${y}`; };
const fmtMonth = (s: string) => { const [y, m] = s.split("-").map(Number); return `${MN[m - 1]} ${y}`; };
const hex2rgb = (h: string) => { h = h.replace("#", ""); if (h.length === 3) h = h.split("").map(c => c + c).join(""); const n = parseInt(h, 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
const mix = (a: string, b: string, t: number) => { const A = hex2rgb(a), B = hex2rgb(b); return "#" + A.map((v, i) => Math.round(v + (B[i] - v) * t).toString(16).padStart(2, "0")).join(""); };
const NS = "http://www.w3.org/2000/svg";
const PAL = {
  light: ["#2a5a9c", "#17808a", "#6a4c9e", "#9c4d7d", "#3a8cc6", "#86673f", "#475878", "#8a6dbb", "#2d6e8e", "#5c7f9e"],
  dark: ["#79a6ea", "#4fc1c9", "#ad92ea", "#e08cbf", "#73c4f2", "#d0ad80", "#94a6cc", "#bba3ef", "#64b0d2", "#a3bcd6"],
};
const VLABEL: Record<string, string> = { HOLDS: "Holds", DISPUTED: "Disputed", MOOT: "Moot", UNDOCUMENTED: "No reason on record", RETIRED: "Retired" };
const SLABEL: Record<string, string> = { expired: "Expired", disputed: "Disputed", holds: "Holds", unevidenced: "Unsurveyed", unchecked: "Unsurveyed" };

const SKELETON = `
<header class="mt-top">
  <div class="mt-titleblock">
    <div class="mt-eyebrow">Decision network of <span class="mt-mono" data-r="tenant"></span></div>
    <h1 class="mt-h1">The lines behind our rules</h1>
    <div class="mt-when"><span>As of <b data-r="asof"></b></span><span class="mt-count" data-r="countLine"></span></div>
  </div>
  <div class="mt-tools">
    <div class="mt-search">
      <input data-r="q" type="search" placeholder="Search the map" autocomplete="off" aria-label="Search stations and lines">
      <kbd>/</kbd>
      <div class="mt-results" data-r="results" role="listbox" hidden></div>
    </div>
    <button class="mt-btn" data-r="queriesBtn" type="button">Queries</button>
  </div>
</header>
<div class="mt-timebar">
  <button class="mt-play" data-r="play" type="button" aria-label="Play the months"><svg viewBox="0 0 12 12" data-r="playIcon"><path d="M2 1 L11 6 L2 11 Z"/></svg></button>
  <div class="mt-tl">
    <div class="mt-track"></div><div class="mt-fill" data-r="tlFill"></div>
    <div data-r="tlMarks"></div>
    <input type="range" data-r="month" min="0" max="1" step="1" value="1" aria-label="Month">
    <div class="mt-knob" data-r="tlKnob"></div>
  </div>
  <div class="mt-mlabel" data-r="mlabel"></div>
</div>
<div class="mt-poster">
  <div class="mt-map" data-r="map" aria-label="Transit map of decisions and the reasons they rest on">
    <svg class="mt-svg" aria-hidden="true"><g data-r="world"></g></svg>
    <div class="mt-labels" data-r="labels"></div>
    <div class="mt-zoomctl">
      <button type="button" data-r="zin" aria-label="Zoom in"><svg viewBox="0 0 14 14"><path d="M7 2v10M2 7h10"/></svg></button>
      <button type="button" data-r="zout" aria-label="Zoom out"><svg viewBox="0 0 14 14"><path d="M2 7h10"/></svg></button>
      <button type="button" data-r="zfit" aria-label="Fit the whole map"><svg viewBox="0 0 14 14"><path d="M1.5 5V1.5H5M9 1.5h3.5V5M12.5 9v3.5H9M5 12.5H1.5V9"/></svg></button>
    </div>
    <div class="mt-banner" data-r="whatif" hidden></div>
    <div class="mt-tip" data-r="tip" hidden></div>
    <aside class="mt-panel" data-r="panel" hidden aria-live="polite"></aside>
  </div>
  <details class="mt-key" data-r="key" open></details>
</div>
<section class="mt-index" data-r="index" aria-label="Stations by verdict"></section>
<footer class="mt-foot">
  <span>Read from FalkorDB graph <span class="mt-mono" data-r="tenant2"></span> · verdicts are path queries over Decision → Premise ← Evidence · nothing on this page writes to the graph.</span>
  <span><button type="button" data-r="queriesBtn2">The Cypher behind this map</button></span>
</footer>
<dialog class="mt-dialog" data-r="queries">
  <h2>Queries</h2>
  <div class="mt-small">The read-only Cypher that reads the network. Verdicts and reason states come from the ledger and audit queries, re-run at every month end.</div>
  <div data-r="qbody"></div>
  <form method="dialog"><button class="mt-btn" type="submit">Close</button></form>
</dialog>`;

export function mountMetro(root: HTMLElement, DATA: MapData, opts: MetroOptions): () => void {
  const ac = new AbortController();
  const sig = { signal: ac.signal };
  const timers = new Set<ReturnType<typeof setTimeout>>();
  const later = (fn: () => void, ms: number) => { const t = setTimeout(() => { timers.delete(t); fn(); }, ms); timers.add(t); return t; };
  let raf = 0, playTimer: ReturnType<typeof setInterval> | null = null, alive = true;

  root.innerHTML = SKELETON;
  const $ = <T extends Element = HTMLElement>(r: string) => root.querySelector(`[data-r="${r}"]`) as unknown as T;
  const MONTHS = DATA.months, LAST = MONTHS.length - 1;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  $("tenant").textContent = DATA.tenant; $("tenant2").textContent = DATA.tenant;
  const range = $<HTMLInputElement>("month"); range.max = String(LAST); range.value = String(LAST);

  /* ---------------- data model ---------------- */
  const byId: Record<string, MapData["nodes"][number]> = {};
  DATA.nodes.forEach(n => { byId[n.id] = n; });
  const decisions = DATA.nodes.filter(n => n.label === "Decision").sort((a, b) => a.id.localeCompare(b.id));
  const premises = DATA.nodes.filter(n => n.label === "Premise");
  const because: Record<string, string[]> = {}, stationsOf: Record<string, string[]> = {}, parentOf: Record<string, string> = {};
  const childrenOf: Record<string, string[]> = {}, evOf: Record<string, Ev[]> = {}, governs: Record<string, string> = {};
  const supersedes: { src: string; dst: string; at: string }[] = [];
  DATA.edges.forEach(e => {
    if (e.rel === "BECAUSE_OF") { (because[e.src] ||= []).push(e.dst); (stationsOf[e.dst] ||= []).push(e.src); }
    else if (e.rel === "DERIVED_FROM") { parentOf[e.src] = e.dst; (childrenOf[e.dst] ||= []).push(e.src); }
    else if (e.rel === "SUPPORTS" || e.rel === "CONTRADICTS") (evOf[e.dst] ||= []).push({ id: e.src, rel: e.rel, at: e.at ?? "", quote: e.quote, p: e.dst });
    else if (e.rel === "SUPERSEDES") supersedes.push({ src: e.src, dst: e.dst, at: e.at ?? "" });
    else if (e.rel === "GOVERNS") governs[e.src] = e.dst;
  });
  Object.values(evOf).forEach(l => l.sort((a, b) => a.at.localeCompare(b.at)));
  const restsOn: Record<string, Set<string>> = {};
  Object.entries(DATA.paths).forEach(([d, rows]) => rows.forEach(r => (restsOn[r.id] ||= new Set()).add(d)));
  const allEv: Ev[] = []; Object.values(evOf).forEach(l => l.forEach(e => allEv.push(e)));
  const ancestors = (p: string) => { const out: string[] = []; let c = parentOf[p]; while (c) { out.push(c); c = parentOf[c]; } return out; };
  const descendants = (p: string): string[] => { const out: string[] = []; (childrenOf[p] || []).forEach(c => { out.push(c); out.push(...descendants(c)); }); return out; };
  const pState = (p: string, m: number): S => (DATA.premise_state[p] || [])[m] ?? null;
  const verdict = (d: string, m: number): V => (DATA.verdicts[d] || [])[m] ?? null;
  const evUpTo = (p: string, m: number) => (evOf[p] || []).filter(e => e.at <= MONTHS[m]);
  const lastOf = (p: string, m: number, rel: string) => { const l = evUpTo(p, m).filter(e => e.rel === rel); return l[l.length - 1] || null; };
  const closedSince = (p: string, m: number) => pState(p, m) === "expired" ? lastOf(p, m, "CONTRADICTS") : null;
  const text = (id: string) => byId[id]?.text ?? id;
  const title = (id: string) => byId[id]?.title ?? id;

  /* ---------------- text measure: the label fonts are the app's own ---------------- */
  const cs = getComputedStyle(root);
  const SANS = cs.getPropertyValue("--m-sans").trim() || "system-ui, sans-serif";
  const SERIF = cs.getPropertyValue("--m-serif").trim() || "Georgia, serif";
  const F = {
    st: `550 13px ${SANS}`, sub: `600 10.5px ${SANS}`, ln: `italic 400 12.5px ${SERIF}`,
    ev: `400 10px ${SANS}`, status: `650 10.5px ${SANS}`, dist: `400 23px ${SERIF}`, net: `400 19px ${SERIF}`, xfer: `italic 400 10px ${SERIF}`,
  };
  const cv = document.createElement("canvas").getContext("2d")!;
  const mw = (t: string, f: string) => { cv.font = f; return cv.measureText(t).width; };
  const greedy = (words: string[], f: string, W: number) => { const lines: string[] = []; let cur = ""; for (const w of words) { const t = cur ? cur + " " + w : w; if (!cur || mw(t, f) <= W) cur = t; else { lines.push(cur); cur = w; } } if (cur) lines.push(cur); return lines; };
  function wrap(s: string, f: string, W: number) { // balanced wrap: same line count as greedy, narrowest width
    const words = s.split(/\s+/); let lines = greedy(words, f, W); const n = lines.length;
    if (n > 1) { let lo = W * 0.45, hi = W; for (let i = 0; i < 14; i++) { const mid = (lo + hi) / 2; if (greedy(words, f, mid).length <= n) hi = mid; else lo = mid; } lines = greedy(words, f, hi); }
    return { lines, w: Math.max(...lines.map(l => mw(l, f))) };
  }

  /* ---------------- districts: connected components (algo.WCC) ---------------- */
  const islands: Record<string, string[]> = {};
  Object.entries(DATA.islands).forEach(([id, c]) => (islands[c] ||= []).push(id));
  const sysName = (s: string) => byId[s]?.name || s;
  function buildDistricts(): District[] {
    const nets: District[] = [], singles: Record<string, { d: string; p: string | null }[]> = {};
    Object.values(islands).forEach(ids => {
      const ds = ids.filter(i => byId[i]?.label === "Decision"), ps = ids.filter(i => byId[i]?.label === "Premise");
      if (ds.length >= 2) {
        // a network is named after the one reason everything in it rests on
        const root = ps.find(p => !parentOf[p]) ?? ps[0];
        nets.push({ kind: "net", root, ds, ps, items: [], name: root ? text(root) : "Network" });
      } else if (ds.length) {
        const d = ds[0], s = governs[d] || "other";
        (singles[s] ||= []).push({ d, p: ps[0] || null });
      }
    });
    nets.sort((a, b) => b.ds.length - a.ds.length || b.ps.length - a.ps.length || (a.root ?? "").localeCompare(b.root ?? ""));
    // single-line islands are grouped by the system their decision governs; small groups merge
    const decided = (d: string) => byId[d].decided_on ?? "";
    const order = (a: { d: string; p: string | null }, b: { d: string; p: string | null }) => (a.p ? 0 : 1) - (b.p ? 0 : 1) || decided(a.d).localeCompare(decided(b.d));
    const sysOrder = Object.keys(singles).sort((a, b) => singles[b].length - singles[a].length || sysName(a).localeCompare(sysName(b)));
    const groups: District[] = []; let acc: { names: string[]; items: { d: string; p: string | null }[] } | null = null;
    sysOrder.forEach(s => {
      const items = singles[s].slice().sort(order);
      if (items.length >= 4) { groups.push({ kind: "sys", name: sysName(s), items, ds: [], ps: [] }); return; }
      if (!acc) acc = { names: [sysName(s)], items: items.slice() };
      else { acc.names.push(sysName(s)); acc.items.push(...items); }
      if (acc.items.length >= 3) { groups.push({ kind: "sys", name: acc.names.map((n, i) => (i ? n.toLowerCase() : n)).join(" and "), items: acc.items.sort(order), ds: [], ps: [] }); acc = null; }
    });
    if (acc) { const a = acc as { names: string[]; items: { d: string; p: string | null }[] }; groups.push({ kind: "sys", name: a.names.map((n, i) => (i ? n.toLowerCase() : n)).join(" and "), items: a.items.sort(order), ds: [], ps: [] }); }
    return nets.concat(groups);
  }
  const DISTRICTS = buildDistricts();

  /* ---------------- line colours ---------------- */
  const orderNet = (root: string): string[] => { const out = [root]; (childrenOf[root] || []).slice().sort().forEach(c => out.push(...orderNet(c))); return out; };
  const lineIdx: Record<string, number> = {};
  { let k = 0;
    DISTRICTS.forEach(dist => {
      const ps = dist.kind === "net" ? orderNet(dist.root!) : dist.items.filter(i => i.p).map(i => i.p!);
      ps.forEach((p, j) => { lineIdx[p] = (k + j) % 10; });
      k = (k + ps.length + 1) % 10;
    }); }

  /* ---------------- layout (deterministic) ---------------- */
  const G = { RU: 94, NAME_W: 176, LBL_W: 162, EVG: 16, STAG: 50, MINRUN: 128, SPMIN: 150, R: 8.5, XF: 74 };
  const weight = (p: string) => { const n = restsOn[p] ? restsOn[p].size : 1; return 6 + 2.4 * Math.max(0, n - 1); };
  const PRE: Record<string, { nm: { lines: string[]; w: number }; evs: Ev[]; evW: number[]; runLen: number; statusW: number }> = {};
  premises.forEach(pr => {
    const p = pr.id, nm = wrap(pr.text ?? p, F.ln, G.NAME_W), evs = evOf[p] || [];
    // each mark reserves room for its label; a break may become "Closed since <date>"
    const evW = evs.map(e => e.rel === "CONTRADICTS" ? mw("Closed since 28 Sep 2026", F.status) : mw("28 Sep 2026", F.ev) + 12);
    const marksLen = evs.length ? 26 + evW.reduce((a, w) => a + w + 10 + G.EVG, 0) : 26 + mw("Unsurveyed", F.status);
    PRE[p] = { nm, evs, evW, runLen: Math.max(nm.w + 26, marksLen, G.MINRUN), statusW: mw("Unsurveyed", F.status) };
  });
  const STL: Record<string, { lines: string[]; w: number }> = {};
  decisions.forEach(d => { STL[d.id] = wrap(d.title ?? d.id, F.st, G.LBL_W); });

  const firstDate = (p: string) => [...(restsOn[p] || [])].map(d => byId[d].decided_on ?? "").sort()[0] || "9999";
  const subRows = (p: string): number => { const ks = childrenOf[p] || []; if (!ks.length) return 1; const s = ks.reduce((a, c) => a + subRows(c), 0); return (stationsOf[p] || []).length ? 1 + s : s; };
  const anchor = (p: string): number => { const ks = childrenOf[p] || []; if (!ks.length || (stationsOf[p] || []).length) return 0.5; if (ks.length === 1) return anchor(ks[0]); return subRows(p) / 2; };
  const depthOf = (p: string): number => { const ks = childrenOf[p] || []; return ks.length ? 1 + Math.max(...ks.map(depthOf)) : 0; };
  const kidsSorted = (p: string) => (childrenOf[p] || []).slice().sort((a, b) => depthOf(a) - depthOf(b) || firstDate(a).localeCompare(firstDate(b)) || a.localeCompare(b));
  const empty = (): Lay => ({ lines: {}, stations: {}, marks: [], labels: [], xfers: [] });

  function placeTree(root: string, x0: number, yTop: number, alignRun?: number): Lay {
    const out = empty();
    function station(d: string, x: number, y: number, w: number, mode: string) {
      const lab = STL[d], r = Math.max(G.R, w / 2 + 3);
      out.stations[d] = { id: d, x, y, r, mode };
      const h = lab.lines.length * 16 + 16;
      if (mode === "right") out.labels.push({ kind: "st", id: d, x: x + r + 9, y: y - h / 2 + 1, w: lab.w, h });
      else out.labels.push({ kind: "st", id: d, x: x - 6, y: y - r - 8 - h, w: lab.w, h });
    }
    function place(p: string, yT: number, fork: Pt | null, isRoot: boolean) {
      const pre = PRE[p], w = weight(p), y = yT + anchor(p) * G.RU, pts: Pt[] = [];
      let runStart: number;
      if (isRoot || !fork) { pts.push([x0, y]); runStart = x0; }
      else { const [fx, fy] = fork; pts.push([fx, fy]); const dy = Math.abs(y - fy); if (dy > 0.5) pts.push([fx + dy, y]); runStart = fx + dy; }
      const ks = kidsSorted(p), own = (stationsOf[p] || []).slice().sort((a, b) => (byId[a].decided_on ?? "").localeCompare(byId[b].decided_on ?? ""));
      const runLen = (isRoot && alignRun) ? alignRun : pre.runLen;
      const nameX = runStart + (isRoot ? 14 : 16);
      out.labels.push({ kind: "ln", id: p, x: nameX, y: y - w / 2 - 8 - pre.nm.lines.length * 15, w: pre.nm.w, h: pre.nm.lines.length * 15 });
      // inspection marks along the run
      let mx = runStart + 30;
      pre.evs.forEach((e, i) => {
        if (i) mx += pre.evW[i - 1] + 10 + G.EVG;
        out.marks.push({ ev: e, p, x: mx, y, w });
        const sup = e.rel === "SUPPORTS";
        out.labels.push({ kind: "ev", id: e.id, p, x: mx + (sup ? 19 : 9), y: y + w / 2 + 5, w: pre.evW[i] - (sup ? 12 : 0), h: 12, rel: e.rel, at: e.at });
      });
      out.labels.push({ kind: "status", id: p, x: runStart + 24, y: y + w / 2 + 5, w: pre.statusW, h: 12 });
      const runEnd = runStart + runLen;
      const L0: Line = { id: p, pts, w, y, runStart, isRoot, knot: null };
      out.lines[p] = L0;
      if (ks.length && !own.length) {
        if (ks.length === 1) {
          pts.push([runEnd, y]); L0.knot = [runEnd, y];
          place(ks[0], yT, [runEnd, y], false);
        } else {
          const S = subRows(p); let cum = 0; const kinfo: { k: string; top: number; ky: number }[] = [];
          ks.forEach(k => { const top = yT + (anchor(p) - S / 2 + cum) * G.RU; kinfo.push({ k, top, ky: top + anchor(k) * G.RU }); cum += subRows(k); });
          const dys = kinfo.map(i => Math.abs(i.ky - y)), minDy = Math.min(...dys);
          const levels = dys.map(d => Math.round((d - minDy) / G.RU)), maxLv = Math.max(...levels);
          const tEnd = runEnd + G.STAG * maxLv;
          pts.push([tEnd, y]); L0.knot = [tEnd, y];
          kinfo.forEach((ki, i) => place(ki.k, ki.top, [tEnd - G.STAG * levels[i], y], false));
        }
      } else {
        let sx0 = runEnd;
        if (ks.length) {
          let cum = 1; ks.forEach((k, i) => { const top = yT + cum * G.RU; place(k, top, [runEnd - G.STAG * i, y], false); cum += subRows(k); });
          sx0 = runEnd + 46;
        }
        let x = sx0;
        if (own.length > 1) x = Math.max(x, nameX + pre.nm.w + 30);
        own.forEach((d, i) => {
          const last = i === own.length - 1;
          pts.push([x, y]);
          station(d, x, y, w, last ? "right" : "above");
          if (!last) x += Math.max(G.SPMIN, STL[d].w + 40);
        });
        if (!own.length) pts.push([runEnd, y]);
      }
      for (let i = pts.length - 1; i > 0; i--) if (Math.abs(pts[i][0] - pts[i - 1][0]) < .1 && Math.abs(pts[i][1] - pts[i - 1][1]) < .1) pts.splice(i, 1);
    }
    place(root, yTop, null, true);
    return out;
  }
  function bboxOf(o: Lay) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    const add = (a: number, b: number, c: number, d: number) => { x0 = Math.min(x0, a); y0 = Math.min(y0, b); x1 = Math.max(x1, c); y1 = Math.max(y1, d); };
    Object.values(o.lines).forEach(l => l.pts.forEach(([x, y]) => add(x - 8, y - l.w, x + 8, y + l.w)));
    Object.values(o.stations).forEach(s => add(s.x - s.r, s.y - s.r, s.x + s.r, s.y + s.r));
    o.labels.forEach(b => add(b.x, b.y, b.x + b.w, b.y + b.h));
    return { x0, y0, x1, y1, w: x1 - x0, h: y1 - y0 };
  }
  function shift(o: Lay, dx: number, dy: number) {
    Object.values(o.lines).forEach(l => { l.pts = l.pts.map(([x, y]) => [x + dx, y + dy] as Pt); l.y += dy; l.runStart += dx; if (l.knot) l.knot = [l.knot[0] + dx, l.knot[1] + dy]; });
    Object.values(o.stations).forEach(s => { s.x += dx; s.y += dy; });
    o.marks.forEach(m => { m.x += dx; m.y += dy; });
    o.labels.forEach(b => { b.x += dx; b.y += dy; });
    o.xfers.forEach(t => { t.a = [t.a[0] + dx, t.a[1] + dy]; t.b = [t.b[0] + dx, t.b[1] + dy]; });
  }
  function merge(dst: Lay, o: Lay) { Object.assign(dst.lines, o.lines); Object.assign(dst.stations, o.stations); dst.marks.push(...o.marks); dst.labels.push(...o.labels); dst.xfers.push(...o.xfers); }
  function isolated(d: string, x: number, y: number, out: Lay, sub: string) {
    const lab = STL[d]; out.stations[d] = { id: d, x, y, r: G.R, mode: "right", lone: true };
    const h = lab.lines.length * 16 + 16;
    out.labels.push({ kind: "st", id: d, x: x + G.R + 9, y: y - h / 2 + 1, w: Math.max(lab.w, mw(sub, F.sub)), h });
  }

  function layoutDistrict(dist: District, cols: number) {
    const o = empty();
    if (dist.kind === "net") {
      const t = placeTree(dist.root!, 0, 0);
      // the district heading is the root reason's text, so its own line label would only repeat it
      t.labels = t.labels.filter(b => !(b.kind === "ln" && b.id === dist.root));
      merge(o, t);
      // decisions in the island with no reason: hang them off the station that supersedes them
      dist.ds.filter(d => !because[d]).forEach(d => {
        const sup = supersedes.find(s => s.dst === d && o.stations[s.src]);
        if (!sup) return;
        const s = o.stations[sup.src], y = s.y + G.XF;
        isolated(d, s.x, y, o, `Retired · replaced by ${sup.src}`);
        o.xfers.push({ a: [s.x, s.y + s.r + 3], b: [s.x, y - G.R - 3], src: sup.src, dst: d, at: sup.at });
        const txt = `superseded ${fmtD(sup.at)}`, tw = mw(txt, F.xfer);
        o.labels.push({ kind: "xfer", id: `${sup.src}>${d}`, x: s.x - 10 - tw, y: s.y + G.XF / 2 - 2, w: tw, h: 12, text: txt });
      });
    } else {
      const rows = dist.items.filter(i => i.p).map(it => ({ it, lone: false })).concat(dist.items.filter(i => !i.p).map(it => ({ it, lone: true })));
      const per = Math.ceil(rows.length / cols);
      let x = 0;
      for (let c = 0; c < cols; c++) {
        const part = rows.slice(c * per, (c + 1) * per); if (!part.length) continue;
        const align = Math.max(G.MINRUN, ...part.filter(r => !r.lone).map(r => PRE[r.it.p!].runLen));
        const col = empty(); let y = 0;
        part.forEach(r => {
          let t: Lay;
          if (!r.lone) t = placeTree(r.it.p!, 0, 0, align);
          else { t = empty(); isolated(r.it.d, align, 0, t, "No line on record"); }
          const b = bboxOf(t); shift(t, 0, y - b.y0 + (r.lone ? 4 : 0)); merge(col, t); y += b.h + (r.lone ? 14 : 20);
        });
        const cb = bboxOf(col); shift(col, x - cb.x0, 0); merge(o, col); x += cb.w + 56;
      }
    }
    const b = bboxOf(o);
    const font = dist.kind === "net" ? F.net : F.dist, lh = dist.kind === "net" ? 23 : 26;
    const head = wrap(dist.name, font, Math.max(220, Math.min(b.w, 520)));
    const top = head.lines.length * lh + 24;
    shift(o, -b.x0, -b.y0 + top);
    const ds = Object.keys(o.stations).length, ls = Object.keys(o.lines).length;
    const sub = `${ds} ${ds === 1 ? "station" : "stations"} · ${ls ? `${ls} ${ls === 1 ? "line" : "lines"}` : "no lines"}`;
    return { o, w: Math.max(b.w, head.w), h: b.h + top, name: head.lines, net: dist.kind === "net", sub };
  }
  type Block = ReturnType<typeof layoutDistrict>;

  // skyline bottom-left packing of district blocks; a deterministic search over widths, orders and column variants
  function skyline(blocks: Block[], W: number, GX: number, GY: number) {
    let sky = [{ x: 0, w: W, y: 0 }]; const pos: { x: number; y: number }[] = [];
    for (const b of blocks) {
      const bw = b.w + GX, bh = b.h + GY; let best: { x: number; y: number } | null = null;
      for (let i = 0; i < sky.length; i++) {
        const x = sky[i].x; if (x + b.w > W + 0.5) break;
        let y = 0, j = i, span = 0;
        while (span < bw && j < sky.length) { y = Math.max(y, sky[j].y); span = sky[j].x + sky[j].w - x; j++; }
        if (span < Math.min(bw, W - x) - 0.5) continue;
        if (!best || y < best.y - 0.5 || (Math.abs(y - best.y) <= 0.5 && x < best.x)) best = { x, y };
      }
      if (!best) return null;
      pos.push(best);
      const nx0 = best.x, nx1 = best.x + bw, ny = best.y + bh, ns: typeof sky = [];
      sky.forEach(sg => {
        const a = sg.x, z = sg.x + sg.w;
        if (z <= nx0 || a >= nx1) { ns.push(sg); return; }
        if (a < nx0) ns.push({ x: a, w: nx0 - a, y: sg.y });
        if (z > nx1) ns.push({ x: nx1, w: z - nx1, y: sg.y });
      });
      ns.push({ x: nx0, w: Math.min(nx1, W) - nx0, y: ny }); ns.sort((p, q) => p.x - q.x);
      sky = ns.filter(sg => sg.w > 0.5);
    }
    return { pos, W: Math.max(...blocks.map((b, i) => pos[i].x + b.w)), H: Math.max(...blocks.map((b, i) => pos[i].y + b.h)) };
  }
  function layoutAll(mode: "narrow" | "wide") {
    const L: Lay & { dists: DistBox[]; W: number; H: number } = { ...empty(), dists: [], W: 0, H: 0 };
    const vars = DISTRICTS.map(d => d.kind === "net" ? [layoutDistrict(d, 1)] : [layoutDistrict(d, 1), layoutDistrict(d, 2)]);
    const GX = 64, GY = 46;
    const vw = Math.max(320, mapEl.clientWidth), vh = Math.max(300, mapEl.clientHeight);
    const nv = vars.map(v => v.length), combos = nv.reduce((a, n) => a * n, 1);
    let best: { k: number; pk: NonNullable<ReturnType<typeof skyline>>; seq: Block[] } | null = null;
    const orders: ((a: Block, b: Block) => number)[] = [(a, b) => b.h - a.h, (a, b) => b.w * b.h - a.w * a.h, (a, b) => b.w - a.w, () => 0];
    for (let c = 0; c < combos; c++) {
      let r = c; const pick = vars.map((v, i) => { const k = r % nv[i]; r = Math.floor(r / nv[i]); return v[k]; });
      if (mode === "narrow" && pick.some((b, i) => vars[i].length > 1 && b !== vars[i][0])) continue;
      const maxW = Math.max(...pick.map(b => b.w));
      for (const ord of orders) {
        const seq = [pick[0], ...pick.slice(1).sort(ord)];
        const widths = mode === "narrow" ? [maxW] : Array.from({ length: 24 }, (_, i) => maxW + i * 90);
        for (const W of widths) {
          const pk = skyline(seq, W, GX, GY); if (!pk) continue;
          const k = mode === "narrow" ? 1 : Math.min(vw / (pk.W + 90), vh / (pk.H + 90));
          if (!best || k > best.k + 1e-4) best = { k, pk, seq };
        }
      }
    }
    best!.seq.forEach((b, i) => { const p = best!.pk.pos[i]; shift(b.o, p.x, p.y); merge(L, b.o); L.dists.push({ name: b.name, net: b.net, sub: b.sub, x: p.x, y: p.y, w: b.w, h: b.h }); });
    L.W = best!.pk.W; L.H = best!.pk.H;
    return L;
  }

  /* ---------------- geometry ---------------- */
  function roundedPath(pts: Pt[], r: number) {
    if (pts.length < 2) return "";
    let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
    for (let i = 1; i < pts.length - 1; i++) {
      const [ax, ay] = pts[i - 1], [bx, by] = pts[i], [cx, cy] = pts[i + 1];
      const l1 = Math.hypot(bx - ax, by - ay), l2 = Math.hypot(cx - bx, cy - by), rr = Math.min(r, l1 / 2, l2 / 2);
      const p1 = [bx - (bx - ax) / l1 * rr, by - (by - ay) / l1 * rr], p2 = [bx + (cx - bx) / l2 * rr, by + (cy - by) / l2 * rr];
      d += ` L${p1[0].toFixed(1)} ${p1[1].toFixed(1)} Q${bx.toFixed(1)} ${by.toFixed(1)} ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
    }
    const e = pts[pts.length - 1]; d += ` L${e[0].toFixed(1)} ${e[1].toFixed(1)}`;
    return d;
  }

  /* ---------------- DOM build ---------------- */
  const mapEl = $("map"), world = $<SVGGElement>("world"), labelsEl = $("labels");
  const mk = (tag: string, attrs: Record<string, string | number>, parent?: Element) => { const e = document.createElementNS(NS, tag) as SVGElement; for (const k in attrs) e.setAttribute(k, String(attrs[k])); if (parent) parent.appendChild(e); return e; };
  type LineRef = { l: Line; ghost: SVGElement; line: SVGElement; bar: SVGElement | null; knot: SVGElement | null };
  type MarkRef = { m: Mark; g: SVGElement; parts: Record<string, SVGElement> };
  type StRef = { s: Station; g: SVGElement; ring: SVGElement; bar: SVGElement; dot: SVGElement; strike: SVGElement };
  let LAY: ReturnType<typeof layoutAll>, MODE: "narrow" | "wide";
  let REF: { lines: Record<string, LineRef>; stations: Record<string, StRef>; marks: MarkRef[]; labels: { b: Box | null; e: HTMLElement }[]; xfers: { t: Xfer; p: SVGElement }[] };

  function build() {
    MODE = mapEl.clientWidth < 700 ? "narrow" : "wide";
    LAY = layoutAll(MODE);
    world.innerHTML = ""; labelsEl.innerHTML = "";
    REF = { lines: {}, stations: {}, marks: [], labels: [], xfers: [] };
    const gLines = mk("g", {}, world), gKnots = mk("g", {}, world), gMarks = mk("g", {}, world), gX = mk("g", {}, world), gSt = mk("g", {}, world), gHit = mk("g", {}, world);
    Object.values(LAY.lines).forEach(l => {
      const d = roundedPath(l.pts, 22), g = mk("g", {}, gLines);
      const ghost = mk("path", { d, fill: "none", "stroke-width": l.w, "stroke-linejoin": "round", "stroke-linecap": "butt" }, g);
      const line = mk("path", { d, fill: "none", "stroke-width": l.w, "stroke-linejoin": "round", "stroke-linecap": "butt" }, g);
      let bar: SVGElement | null = null, knot: SVGElement | null = null;
      if (l.isRoot) { const [x, y] = l.pts[0]; bar = mk("line", { x1: x, y1: y - l.w / 2 - 6, x2: x, y2: y + l.w / 2 + 6, "stroke-width": 4, "stroke-linecap": "round" }, gKnots); }
      if (l.knot) knot = mk("circle", { cx: l.knot[0], cy: l.knot[1], r: l.w / 2 + .2 }, gKnots);
      mk("path", { d, fill: "none", stroke: "transparent", "stroke-width": Math.max(18, l.w + 12), "data-kind": "line", "data-id": l.id, style: "pointer-events:stroke;cursor:pointer" }, gHit);
      REF.lines[l.id] = { l, ghost, line, bar, knot };
    });
    LAY.marks.forEach(m => {
      const g = mk("g", { "data-kind": "ev", "data-id": m.ev.id, "data-p": m.p, style: "cursor:pointer" }, gMarks), h = m.w / 2;
      let parts: Record<string, SVGElement>;
      if (m.ev.rel === "CONTRADICTS") {
        const gap = mk("polygon", { points: `${m.x - 6},${m.y + h + 4} ${m.x + 1},${m.y - h - 4} ${m.x + 6},${m.y - h - 4} ${m.x - 1},${m.y + h + 4}` }, g);
        const s1 = mk("line", { x1: m.x - 6, y1: m.y + h + 5, x2: m.x + 1, y2: m.y - h - 5, "stroke-width": 2.4, "stroke-linecap": "round" }, g);
        const s2 = mk("line", { x1: m.x - 1, y1: m.y + h + 5, x2: m.x + 6, y2: m.y - h - 5, "stroke-width": 2.4, "stroke-linecap": "round" }, g);
        parts = { gap, s1, s2 };
      } else {
        const tick = mk("line", { x1: m.x, y1: m.y - h - 4, x2: m.x, y2: m.y + h + 5, "stroke-width": 2, "stroke-linecap": "round" }, g);
        const chk = mk("path", { d: `M${m.x + 5} ${m.y + h + 8.6} l2.5 2.5 l5 -5.4`, fill: "none", "stroke-width": 1.9, "stroke-linecap": "round", "stroke-linejoin": "round" }, g);
        parts = { tick, chk };
      }
      mk("rect", { x: m.x - 9, y: m.y - h - 12, width: 18, height: m.w + 24, fill: "transparent" }, g);
      REF.marks.push({ m, g, parts });
    });
    LAY.xfers.forEach(t => REF.xfers.push({ t, p: mk("line", { x1: t.a[0], y1: t.a[1], x2: t.b[0], y2: t.b[1], "stroke-width": 3.2, "stroke-linecap": "round", "stroke-dasharray": "0.1 6.5" }, gX) }));
    Object.values(LAY.stations).forEach(s => {
      const g = mk("g", { "data-kind": "st", "data-id": s.id, style: "cursor:pointer" }, gSt);
      const ring = mk("circle", { cx: s.x, cy: s.y, r: s.r, "stroke-width": 2.6 }, g);
      const bar = mk("rect", { x: s.x - s.r * 0.55, y: s.y - 1.3, width: s.r * 1.1, height: 2.6, rx: 1 }, g);
      const dot = mk("circle", { cx: s.x, cy: s.y, r: 2.6 }, g);
      const strike = mk("line", { x1: s.x - s.r - 4, y1: s.y + s.r + 4, x2: s.x + s.r + 4, y2: s.y - s.r - 4, "stroke-width": 2.2, "stroke-linecap": "round" }, g);
      mk("circle", { cx: s.x, cy: s.y, r: s.r + 7, fill: "transparent" }, g);
      REF.stations[s.id] = { s, g, ring, bar, dot, strike };
    });
    LAY.dists.forEach(d => {
      const e = document.createElement("div"); e.className = `mt-lbl mt-dist${d.net ? " net" : ""}`; e.style.left = `${d.x}px`; e.style.top = `${d.y}px`;
      e.innerHTML = `${d.name.map(esc).join("<br>")}<small>${esc(d.sub)}</small>`; labelsEl.appendChild(e); REF.labels.push({ b: null, e });
    });
    LAY.labels.forEach(b => {
      let e: HTMLElement;
      if (b.kind === "st") {
        const btn = document.createElement("button"); btn.type = "button"; e = btn; e.className = "mt-lbl mt-st";
        e.innerHTML = `<span class="t">${STL[b.id].lines.map(esc).join("<br>")}</span><span class="v"></span>`;
        e.setAttribute("aria-label", `${b.id} ${title(b.id)}`);
      } else if (b.kind === "ln") {
        e = document.createElement("div"); e.className = "mt-lbl mt-ln-name";
        e.innerHTML = PRE[b.id].nm.lines.map(l => `<span>${esc(l)}</span>`).join("");
      } else if (b.kind === "ev") {
        e = document.createElement("div"); e.className = "mt-lbl mt-ev-d"; e.dataset.p = b.p; e.textContent = fmtD(b.at);
      } else if (b.kind === "status") {
        e = document.createElement("div"); e.className = "mt-lbl mt-status unsurveyed";
      } else {
        e = document.createElement("div"); e.className = "mt-lbl mt-xfer"; e.textContent = b.text ?? "";
      }
      if (b.kind !== "xfer") { e.dataset.kind = b.kind === "st" ? "st" : b.kind === "ev" ? "ev" : "line"; e.dataset.id = b.id; }
      e.style.left = `${b.x.toFixed(1)}px`; e.style.top = `${b.y.toFixed(1)}px`;
      labelsEl.appendChild(e); REF.labels.push({ b, e });
    });
  }

  /* ---------------- state ---------------- */
  let month = LAST, hover: Target | null = null, selected: Target | null = null, preview: Preview | null = null;
  let theme: { dark: boolean; bg: string; ink: string; ink2: string; ink3: string; fill: string; red: string; holds: string; holdsT: string; disp: string; dispT: string; pal: string[] };
  function trailOf(t: Target | null) {
    if (!t) return null;
    const s = new Set<string>();
    if (t.kind === "st") {
      const d = t.id; s.add(d);
      (DATA.paths[d] || []).forEach(r => s.add(r.id));
      (because[d] || []).forEach(p => { s.add(p); ancestors(p).forEach(a => s.add(a)); });
      supersedes.forEach(x => { if (x.src === d || x.dst === d) { s.add(x.src); s.add(x.dst); s.add(`xf:${x.src}>${x.dst}`); } });
    } else {
      const p = t.kind === "ev" ? t.p! : t.id;
      s.add(p); ancestors(p).forEach(a => s.add(a)); descendants(p).forEach(c => s.add(c));
      (restsOn[p] || new Set()).forEach(d => s.add(d));
      if (t.kind === "ev") s.add(`ev:${t.id}`);
    }
    [...s].forEach(id => { if (byId[id]?.label === "Premise") (evOf[id] || []).forEach(e => s.add(`ev:${e.id}`)); });
    return s;
  }
  function readTheme() {
    const c = getComputedStyle(root), g = (n: string) => c.getPropertyValue(n).trim();
    const t = document.documentElement.dataset.theme;
    const dark = t === "dark" || (!t && matchMedia("(prefers-color-scheme: dark)").matches);
    theme = { dark, bg: g("--m-map-bg"), ink: g("--m-map-ink"), ink2: g("--m-map-ink2"), ink3: g("--m-map-ink3"), fill: g("--m-st-fill"), red: g("--m-red"),
      holds: g("--m-holds-mark"), holdsT: g("--m-holds"), disp: g("--m-disputed-mark"), dispT: g("--m-disputed"), pal: dark ? PAL.dark : PAL.light };
  }

  function render() {
    const T = theme, m = month;
    const trail = preview ? trailOf({ kind: "line", id: preview.p }) : trailOf(hover || selected);
    const fade = (c: string, id: string) => (trail && !trail.has(id)) ? mix(c, T.bg, T.dark ? 0.8 : 0.84) : c;
    const ghostC = (c: string) => mix(c, T.bg, T.dark ? 0.86 : 0.88);
    Object.values(REF.lines).forEach(R => {
      const p = R.l.id, isPrev = preview?.p === p;
      let st = pState(p, m);
      if (isPrev) st = "expired";
      const base = T.pal[lineIdx[p] ?? 0];
      let c: string, dash: string | null = null;
      if (st == null) c = ghostC(base);
      else if (st === "expired") { c = T.red; dash = isPrev ? "2 7" : "8 6"; }
      else if (st === "unevidenced" || st === "unchecked") { c = base; dash = "10 6.5"; }
      else c = base;
      const cf = st == null ? c : fade(c, p);
      R.line.style.stroke = cf; R.line.setAttribute("stroke-dasharray", dash || "none");
      R.line.setAttribute("stroke-linecap", isPrev ? "round" : "butt");
      // a faint solid bed under dashed lines keeps the route legible
      R.ghost.style.stroke = (dash && st != null) ? mix(cf, T.bg, st === "expired" ? 0.82 : 0.8) : "transparent";
      if (R.bar) R.bar.style.stroke = cf;
      if (R.knot) R.knot.style.fill = cf;
    });
    REF.marks.forEach(R => {
      const on = R.m.ev.at <= MONTHS[m];
      R.g.style.display = on ? "" : "none";
      if (!on) return;
      const id = `ev:${R.m.ev.id}`;
      if (R.parts.gap) { R.parts.gap.style.fill = fade(T.bg, id); R.parts.s1.style.stroke = fade(T.red, id); R.parts.s2.style.stroke = fade(T.red, id); }
      else { R.parts.tick.style.stroke = fade(T.ink2, id); R.parts.chk.style.stroke = fade(T.holds, id); }
    });
    REF.xfers.forEach(R => { R.p.style.display = R.t.at <= MONTHS[m] ? "" : "none"; R.p.style.stroke = fade(T.ink3, `xf:${R.t.src}>${R.t.dst}`); });
    Object.values(REF.stations).forEach(R => {
      const d = R.s.id, v = verdict(d, m), wouldMoot = !!preview && preview.flips.has(d) && !!v;
      let ring: string, fill: string, bar = "none", dot = "none", strike = "none", dash = "none";
      if (v == null) { ring = ghostC(T.ink3); fill = T.bg; }
      else if (v === "MOOT") { ring = T.red; fill = T.red; bar = T.dark ? T.bg : "#fff8f2"; }
      else if (v === "DISPUTED") { ring = T.disp; fill = T.fill; dot = T.disp; }
      else if (v === "UNDOCUMENTED") { ring = T.ink3; fill = T.fill; dash = "2.6 2.2"; }
      else if (v === "RETIRED") { ring = T.ink3; fill = T.fill; strike = T.ink2; }
      else { ring = T.ink; fill = T.fill; }
      if (wouldMoot) { ring = T.red; fill = T.fill; dot = T.red; dash = "none"; }
      const f = (c: string) => (v == null || c === "none") ? c : fade(c, d);
      R.ring.style.stroke = f(ring); R.ring.style.fill = v == null ? T.bg : f(fill); R.ring.setAttribute("stroke-dasharray", dash);
      R.ring.setAttribute("stroke-width", v == null ? "1.6" : "2.6");
      R.bar.style.fill = f(bar); R.bar.style.display = bar === "none" ? "none" : "";
      R.dot.style.fill = f(dot); R.dot.style.display = dot === "none" ? "none" : "";
      R.strike.style.stroke = f(strike); R.strike.style.display = strike === "none" ? "none" : "";
      R.g.style.filter = (T.dark && v === "MOOT" && !(trail && !trail.has(d))) ? "drop-shadow(0 0 4px rgba(255,122,99,.55))" : "";
    });
    REF.labels.forEach(({ b, e }) => {
      if (!b) return;
      if (b.kind === "st") {
        const v = verdict(b.id, m), wouldMoot = !!preview && preview.flips.has(b.id) && !!v;
        const t = e.firstChild as HTMLElement, sub = e.lastChild as HTMLElement, lone = !because[b.id];
        let txt: string, col: string;
        if (v == null) { txt = `Opens ${fmtD(byId[b.id].decided_on)}`; col = T.ink3; }
        else if (wouldMoot) { txt = "Would lose its line"; col = T.red; }
        else if (v === "MOOT") { txt = "Moot · line closed"; col = T.red; }
        else if (v === "DISPUTED") { txt = "Disputed · owner to rule"; col = T.dispT; }
        else if (v === "UNDOCUMENTED") { txt = lone ? "No line on record" : "No reason on record"; col = T.ink3; }
        else if (v === "RETIRED") { const s = supersedes.find(x => x.dst === b.id); txt = `Retired${s ? ` · replaced by ${s.src}` : ""}`; col = T.ink3; }
        else { txt = "Holds"; col = T.holdsT; }
        sub.textContent = txt;
        t.style.color = v == null ? ghostC(T.ink) : fade(T.ink, b.id);
        sub.style.color = v == null ? mix(T.ink3, T.bg, .45) : fade(col, b.id);
        e.classList.toggle("retired", v === "RETIRED");
      } else if (b.kind === "ln") {
        e.style.color = pState(b.id, m) == null ? ghostC(T.ink2) : fade(T.ink2, b.id);
      } else if (b.kind === "ev") {
        const on = (b.at ?? "") <= MONTHS[m]; e.style.display = on ? "" : "none";
        if (!on) return;
        const c = b.rel === "CONTRADICTS" && preview?.p !== b.p ? closedSince(b.p!, m) : null, closing = !!c && c.id === b.id;
        e.textContent = closing ? `Closed since ${fmtD(b.at)}` : fmtD(b.at);
        e.classList.toggle("mt-status", closing);
        e.style.color = fade(b.rel === "CONTRADICTS" ? T.red : T.ink3, `ev:${b.id}`);
      } else if (b.kind === "status") {
        const st = pState(b.id, m), show = (st === "unevidenced" || st === "unchecked") && !evUpTo(b.id, m).length;
        e.textContent = show ? "Unsurveyed" : ""; e.style.display = show ? "" : "none";
        e.style.color = fade(T.ink3, b.id);
      } else if (b.kind === "xfer") {
        const s = supersedes.find(x => b.id === `${x.src}>${x.dst}`);
        e.style.display = s && s.at <= MONTHS[m] ? "" : "none";
        e.style.color = fade(T.ink3, `xf:${b.id}`);
      }
    });
    renderChrome();
  }

  /* ---------------- chrome: title block, timebar ---------------- */
  function renderChrome() {
    const m = month, open = decisions.filter(d => verdict(d.id, m) != null);
    const moot = open.filter(d => verdict(d.id, m) === "MOOT").length, disp = open.filter(d => verdict(d.id, m) === "DISPUTED").length;
    $("countLine").innerHTML = `<b${moot ? "" : ' style="color:var(--m-ink)"'}>${moot}</b> ${moot === 1 ? "station" : "stations"} on closed lines <span class="sep">·</span> ${disp} disputed <span class="sep">·</span> ${open.length} open`;
    $("asof").textContent = fmtLong(MONTHS[m]);
    $("mlabel").textContent = fmtMonth(MONTHS[m]);
    const pct = LAST ? m / LAST * 100 : 100;
    $("tlFill").style.width = `${pct}%`; $("tlKnob").style.left = `${pct}%`;
    range.value = String(m); range.setAttribute("aria-valuetext", fmtMonth(MONTHS[m]));
  }
  function buildTimeline() {
    let h = "";
    MONTHS.forEach((d, i) => {
      const x = LAST ? i / LAST * 100 : 0, [y, mo] = d.split("-").map(Number);
      if (mo === 1 || i === 0) h += `<div class="mt-tick" style="left:${x}%"></div><div class="mt-yr" style="left:${x}%">${y}</div>`;
    });
    // contradictions on the timeline in brick red, inspections in green
    allEv.forEach(e => {
      const i = MONTHS.findIndex(d => d >= e.at); if (i < 0) return;
      const x = LAST ? i / LAST * 100 : 0;
      h += `<div class="mt-ev" style="left:calc(${x}% - 1px);background:${e.rel === "CONTRADICTS" ? "var(--m-red)" : "var(--m-holds-mark)"}"></div>`;
    });
    $("tlMarks").innerHTML = h;
  }

  /* ---------------- key ---------------- */
  function buildKey() {
    const T = theme, c1 = T.pal[0], c2 = T.pal[1];
    const sw = (inner: string, w = 34) => `<svg width="${w}" height="16" viewBox="0 0 ${w} 16">${inner}</svg>`;
    const st = (ring: string, fill: string, extra = "") => `<circle cx="8" cy="8" r="6" stroke="${ring}" fill="${fill}" stroke-width="2.4"/>${extra}`;
    const items: [string, string][] = [
      [sw(`<line x1="1" y1="8" x2="33" y2="8" stroke="${c1}" stroke-width="5"/>`), "A reason"],
      [sw(`<line x1="1" y1="5" x2="33" y2="5" stroke="${c2}" stroke-width="3"/><line x1="1" y1="12" x2="33" y2="12" stroke="${c2}" stroke-width="7"/>`), "Heavier = more rules rest on it"],
      [sw(`<path d="M1 11 H13 Q16 11 18 9 L21 6 Q23 4 26 4 H33" fill="none" stroke="${c2}" stroke-width="3.5"/><path d="M1 11 H33" stroke="${c1}" stroke-width="5" fill="none"/><circle cx="13" cy="11" r="2.6" fill="${c1}"/>`), "Branch off a deeper reason"],
      [sw(`<line x1="1" y1="8" x2="33" y2="8" stroke="${mix(c1, T.bg, .8)}" stroke-width="5"/><line x1="1" y1="8" x2="33" y2="8" stroke="${c1}" stroke-width="5" stroke-dasharray="8 5"/>`), "Unsurveyed: no dated evidence"],
      [sw(`<line x1="1" y1="8" x2="33" y2="8" stroke="${mix(T.red, T.bg, .82)}" stroke-width="5"/><line x1="1" y1="8" x2="33" y2="8" stroke="${T.red}" stroke-width="5" stroke-dasharray="7 5"/>`), "Closed: the reason expired"],
      [sw(`<line x1="1" y1="9" x2="33" y2="9" stroke="${c1}" stroke-width="5"/><line x1="12" y1="3" x2="12" y2="15" stroke="${T.ink2}" stroke-width="2"/><path d="M15.5 4.5 l2.4 2.4 l4.6 -5" fill="none" stroke="${T.holds}" stroke-width="1.8" stroke-linecap="round"/>`), "Inspection: evidence supports it"],
      [sw(`<line x1="1" y1="8" x2="33" y2="8" stroke="${c1}" stroke-width="5"/><polygon points="11,15 18,1 23,1 16,15" fill="${T.bg}"/><line x1="11" y1="15" x2="18" y2="1" stroke="${T.red}" stroke-width="2.2"/><line x1="16" y1="15" x2="23" y2="1" stroke="${T.red}" stroke-width="2.2"/>`), "Break: evidence contradicts it"],
      [sw(st(T.ink, T.fill), 16), "Holds"],
      [sw(st(T.disp, T.fill, `<circle cx="8" cy="8" r="2.4" fill="${T.disp}"/>`), 16), "Disputed"],
      [sw(st(T.red, T.red, `<rect x="4.6" y="6.8" width="6.8" height="2.4" rx="1" fill="${T.dark ? T.bg : "#fff8f2"}"/>`), 16), "Moot"],
      [sw(`<circle cx="8" cy="8" r="6" stroke="${T.ink3}" fill="${T.fill}" stroke-width="2.2" stroke-dasharray="2.4 2"/>`, 16), "No line on record"],
      [sw(st(T.ink3, T.fill, `<line x1="1" y1="15" x2="15" y2="1" stroke="${T.ink2}" stroke-width="2" stroke-linecap="round"/>`), 16), "Retired"],
      [sw(`<line x1="3" y1="8" x2="31" y2="8" stroke="${T.ink3}" stroke-width="3" stroke-linecap="round" stroke-dasharray="0.1 6"/>`), "Superseded by"],
    ];
    $("key").innerHTML = `<summary>Key</summary><div class="mt-keyrow"><span class="h">Key</span>${items.map(([s, t]) => `<span class="i">${s}<span>${t}</span></span>`).join("")}</div>`;
  }

  /* ---------------- pan and zoom ---------------- */
  const view = { k: 1, x: 0, y: 0 };
  let kMin = 0.2; const kMax = 3;
  function applyView() {
    world.setAttribute("transform", `translate(${view.x.toFixed(2)} ${view.y.toFixed(2)}) scale(${view.k.toFixed(4)})`);
    labelsEl.style.transform = `translate(${view.x.toFixed(2)}px,${view.y.toFixed(2)}px) scale(${view.k.toFixed(4)})`;
  }
  function fitBox(x0: number, y0: number, x1: number, y1: number, pad = 36) {
    const W = mapEl.clientWidth, H = mapEl.clientHeight, k = Math.min((W - pad * 2) / (x1 - x0), (H - pad * 2) / (y1 - y0));
    return { k, x: (W - (x1 - x0) * k) / 2 - x0 * k, y: (H - (y1 - y0) * k) / 2 - y0 * k };
  }
  function worldBox(): [number, number, number, number] {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    [...LAY.labels, ...LAY.dists.map(d => ({ x: d.x, y: d.y, w: d.w, h: 40 }))].forEach(b => { x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y); x1 = Math.max(x1, b.x + b.w); y1 = Math.max(y1, b.y + b.h); });
    Object.values(LAY.lines).forEach(l => l.pts.forEach(([x, y]) => { x0 = Math.min(x0, x - 10); x1 = Math.max(x1, x + 10); y0 = Math.min(y0, y - 10); y1 = Math.max(y1, y + 10); }));
    return [x0, y0, x1, y1];
  }
  function flyTo(t: { k: number; x: number; y: number }, ms: number) {
    cancelAnimationFrame(raf);
    if (reduceMotion || !ms) { Object.assign(view, t); applyView(); return; }
    const s = { ...view }, t0 = performance.now();
    const step = (now: number) => {
      const u = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - u, 3);
      view.k = s.k + (t.k - s.k) * e; view.x = s.x + (t.x - s.x) * e; view.y = s.y + (t.y - s.y) * e; applyView();
      if (u < 1 && alive) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
  }
  function fitAll(ms: number) {
    const [x0, y0, x1, y1] = worldBox();
    const f = fitBox(x0, y0, x1 + (MODE === "narrow" ? 0 : 60 / Math.max(.3, fitBox(x0, y0, x1, y1, 30).k)), y1, MODE === "narrow" ? 14 : 28);
    kMin = f.k * 0.7;
    if (MODE === "narrow") {
      const d0 = LAY.dists[0];
      f.k = Math.max(0.48, Math.min(0.8, (mapEl.clientWidth - 16) / d0.w)); f.x = 10 - d0.x * f.k; f.y = 6 - d0.y * f.k;
      kMin = Math.min(kMin, f.k * 0.5);
    }
    flyTo(f, ms);
  }
  function zoomAt(px: number, py: number, factor: number) {
    const k = Math.max(kMin, Math.min(kMax, view.k * factor)), f = k / view.k;
    view.x = px - (px - view.x) * f; view.y = py - (py - view.y) * f; view.k = k; applyView();
  }
  function focusOn(ids: string[]) {
    const pts: Pt[] = [];
    ids.forEach(id => { const s = LAY.stations[id]; if (s) pts.push([s.x, s.y]); const l = LAY.lines[id]; if (l) l.pts.forEach(p => pts.push(p)); });
    if (!pts.length) return;
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    const W = mapEl.clientWidth, H = mapEl.clientHeight, panelW = (!$("panel").hidden && W > 760) ? 400 : 0;
    const k = Math.max(view.k, Math.min(1.1, (W - panelW - 120) / (Math.max(...xs) - Math.min(...xs) + 260)));
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2 + 80, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    flyTo({ k, x: (W - panelW) / 2 - cx * k, y: (W > 760 ? H / 2 : H * 0.3) - cy * k }, 520);
  }
  const inChrome = (t: EventTarget | null) => !!(t as Element | null)?.closest?.(".mt-zoomctl,.mt-panel,.mt-banner");
  { // pointer: drag to pan, pinch and wheel to zoom, click to select
    const pts = new Map<number, Pt>(); let start: { x: number; y: number; vx: number; vy: number } | null = null, moved = false, pinch: { d: number; k: number } | null = null;
    mapEl.addEventListener("pointerdown", e => {
      if (inChrome(e.target)) return;
      pts.set(e.pointerId, [e.clientX, e.clientY]);
      if (pts.size === 1) { start = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }; moved = false; }
      if (pts.size === 2) { const [a, b] = [...pts.values()]; pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), k: view.k }; }
    }, sig);
    window.addEventListener("pointermove", e => {
      if (!pts.has(e.pointerId)) return;
      pts.set(e.pointerId, [e.clientX, e.clientY]);
      const r = mapEl.getBoundingClientRect();
      if (pts.size === 2 && pinch) { const [a, b] = [...pts.values()]; const d = Math.hypot(a[0] - b[0], a[1] - b[1]); zoomAt((a[0] + b[0]) / 2 - r.left, (a[1] + b[1]) / 2 - r.top, (pinch.k * d / pinch.d) / view.k); moved = true; return; }
      if (start) {
        const dx = e.clientX - start.x, dy = e.clientY - start.y;
        if (!moved && Math.hypot(dx, dy) > 4) { moved = true; mapEl.classList.add("dragging"); try { mapEl.setPointerCapture(e.pointerId); } catch { /* already released */ } }
        if (moved) { view.x = start.vx + dx; view.y = start.vy + dy; applyView(); }
      }
    }, sig);
    const end = (e: PointerEvent) => { if (!pts.has(e.pointerId)) return; pts.delete(e.pointerId); if (pts.size < 2) pinch = null; if (!pts.size) { mapEl.classList.remove("dragging"); start = null; later(() => { moved = false; }, 0); } };
    window.addEventListener("pointerup", end, sig); window.addEventListener("pointercancel", end, sig);
    mapEl.addEventListener("wheel", e => { e.preventDefault(); const r = mapEl.getBoundingClientRect(); zoomAt(e.clientX - r.left, e.clientY - r.top, Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0018))); }, { passive: false, signal: ac.signal });
    mapEl.addEventListener("dblclick", e => { if (inChrome(e.target)) return; const r = mapEl.getBoundingClientRect(); zoomAt(e.clientX - r.left, e.clientY - r.top, 1.6); }, sig);
    mapEl.addEventListener("click", e => {
      if (moved || inChrome(e.target)) return;
      const t = targetOf(e.target);
      if (t) select(t); else clearAll();
    }, sig);
    mapEl.addEventListener("pointerover", e => { if (e.pointerType !== "touch") setHover(targetOf(e.target)); }, sig);
    mapEl.addEventListener("pointermove", e => { if (e.pointerType === "touch" || pts.size) { hideTip(); return; } showTip(targetOf(e.target), e); }, sig);
    mapEl.addEventListener("pointerleave", () => { setHover(null); hideTip(); }, sig);
    $("zin").addEventListener("click", () => zoomAt(mapEl.clientWidth / 2, mapEl.clientHeight / 2, 1.4), sig);
    $("zout").addEventListener("click", () => zoomAt(mapEl.clientWidth / 2, mapEl.clientHeight / 2, 1 / 1.4), sig);
    $("zfit").addEventListener("click", () => fitAll(420), sig);
  }
  function hideTip() { $("tip").hidden = true; }
  function showTip(t: Target | null, e: PointerEvent) {
    const tip = $("tip");
    if (!t || inChrome(e.target)) { tip.hidden = true; return; }
    let h: string;
    if (t.kind === "st") {
      const v = verdict(t.id, month);
      h = `<div class="tt">${esc(title(t.id))}</div><div class="ts"><span class="mt-mono">${t.id}</span> · ${v ? `<b style="color:${({ MOOT: "var(--m-accent)", DISPUTED: "var(--m-disputed)", HOLDS: "var(--m-holds)" } as Record<string, string>)[v] || "var(--m-ink-2)"}">${VLABEL[v]}</b>` : `opens ${fmtD(byId[t.id].decided_on)}`}</div>`;
    } else {
      const p = t.kind === "ev" ? t.p! : t.id, st = pState(p, month);
      let ev = "";
      if (t.kind === "ev") { const x = (evOf[p] || []).find(z => z.id === t.id)!; ev = `<div class="ts"><b style="color:${x.rel === "CONTRADICTS" ? "var(--m-accent)" : "var(--m-holds)"}">${x.rel === "CONTRADICTS" ? "Break" : "Inspection"}</b> · ${fmtD(x.at)} · ${esc(title(x.id))}</div>`; }
      h = `<div class="tt">${esc(text(p))}</div><div class="ts">Line · ${st ? `<b style="color:${({ expired: "var(--m-accent)", disputed: "var(--m-disputed)", holds: "var(--m-holds)" } as Record<string, string>)[st] || "var(--m-ink-2)"}">${st === "expired" ? "Closed" : SLABEL[st]}</b>` : "not in use yet"} · ${restsOn[p] ? restsOn[p].size : 0} resting</div>${ev}`;
    }
    tip.innerHTML = h; tip.hidden = false;
    const r = mapEl.getBoundingClientRect(); let x = e.clientX - r.left + 14, y = e.clientY - r.top + 16;
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    if (x + tw > r.width - 8) x = e.clientX - r.left - tw - 14;
    if (y + th > r.height - 8) y = e.clientY - r.top - th - 12;
    tip.style.left = `${x}px`; tip.style.top = `${y}px`;
  }
  function targetOf(el: EventTarget | null): Target | null {
    const h = (el as Element | null)?.closest?.("[data-kind]") as HTMLElement | SVGElement | null;
    if (!h || !root.contains(h)) return null;
    const kind = h.dataset.kind as Target["kind"], id = h.dataset.id!;
    return kind === "ev" ? { kind, id, p: h.dataset.p } : { kind, id };
  }
  const same = (a: Target | null, b: Target | null) => (!a && !b) || (!!a && !!b && a.kind === b.kind && a.id === b.id);
  function setHover(t: Target | null) { if (same(t, hover)) return; hover = t; render(); }

  /* ---------------- selection and the details panel ---------------- */
  function select(t: Target, fly = false) {
    if (preview) endPreview(true);
    hideTip();
    if (t.kind === "ev") t = { kind: "line", id: t.p!, ev: t.id };
    selected = t; hover = null; render(); openPanel(t);
    if (fly) focusOn(t.kind === "st" ? [t.id, ...(because[t.id] || [])] : [t.id, ...(restsOn[t.id] ? [...restsOn[t.id]] : [])]);
  }
  function clearAll() { selected = null; hover = null; if (preview) endPreview(true); $("panel").hidden = true; mapEl.classList.remove("has-panel"); render(); }
  const pill = (cls: string, txt: string) => `<span class="mt-pill ${cls}">${esc(txt)}</span>`;
  const vPill = (v: V) => v == null ? pill("q", "Not decided yet") : pill(v.toLowerCase(), VLABEL[v] ?? v);
  const sPill = (s: S) => s == null ? pill("q", "Not in use yet") : pill(s, SLABEL[s] ?? s);
  const person = (id: string) => byId[id]?.name ?? id;
  function evHtml(e: Ev) {
    const n = byId[e.id] || {};
    return `<div class="mt-evi"><div class="eh"><b class="${e.rel === "CONTRADICTS" ? "c" : "s"}">${e.rel === "CONTRADICTS" ? "Contradicts" : "Supports"}</b><span>${fmtD(e.at)}</span><span class="mt-small">· ${esc(n.title ?? "")} <span class="mt-mono">${esc(e.id)}</span>${n.author ? ` · ${esc(person(n.author))}` : ""}</span></div><q>${esc(e.quote || n.excerpt || "")}</q></div>`;
  }
  function whyStation(d: string, m: number) {
    const v = verdict(d, m), rows = DATA.paths[d] || [], t = (p: string) => `“${text(p)}”`;
    if (v == null) return `Not decided yet; this station opens on ${fmtLong(byId[d].decided_on ?? "")}.`;
    if (v === "RETIRED") { const s = supersedes.find(x => x.dst === d); return s ? `Retired on ${fmtLong(s.at)}, when ${s.src} (${title(s.src)}) superseded it. It no longer needs a reason.` : "Retired."; }
    if (v === "UNDOCUMENTED" && !rows.length) return "No reason is recorded, so there is no line to check it against.";
    if (v === "MOOT") {
      const r = rows.filter(r => pState(r.id, m) === "expired").sort((a, b) => a.hops - b.hops)[0], c = r && closedSince(r.id, m);
      if (r && c) {
        const via = r.hops > 1 ? `It rides ${t(r.path[1])}, which branches off ${t(r.id)}. That deeper reason` : `Its line, ${t(r.id)},`;
        return `${via} closed on ${fmtLong(c.at)}, contradicted by “${title(c.id)}” (${c.id}). The rule is still enforced; its reason no longer runs.`;
      }
    }
    if (v === "DISPUTED") {
      const r = rows.find(r => pState(r.id, m) === "disputed"), c = r && lastOf(r.id, m, "CONTRADICTS"), s = r && lastOf(r.id, m, "SUPPORTS");
      if (r && c && s && s.at >= c.at) return `${t(r.id)} was contradicted on ${fmtLong(c.at)} and re-affirmed on ${fmtLong(s.at)}; the owner has to rule.`;
      if (r && c) return `${t(r.id)} was flagged on ${fmtLong(c.at)} by a licence or vulnerability check that no stated reason depends on; the owner has to rule.`;
    }
    const direct = rows.find(r => r.hops === 1);
    if (!direct) return "Holds.";
    const last = lastOf(direct.id, m, "SUPPORTS");
    let s = pState(direct.id, m) === "holds" && last ? `Its reason ${t(direct.id)} was last inspected on ${fmtLong(last.at)} and nothing has contradicted it since.` : `Nothing contradicts ${t(direct.id)}, but no one has inspected it either.`;
    const deep = rows.filter(r => r.hops > 1 && (pState(r.id, m) === "unevidenced" || pState(r.id, m) === "unchecked"));
    if (deep.length) s += ` The deeper reason ${t(deep[deep.length - 1].id)} has never been inspected.`;
    return s;
  }
  function openPanel(t: Target) {
    const P = $("panel"), m = month; let h = '<button class="x" type="button" aria-label="Close details">&times;</button>';
    if (t.kind === "st") {
      const d = byId[t.id], v = verdict(t.id, m), rows = DATA.paths[t.id] || [];
      h += `<div class="p-id">${esc(t.id)} · station · decided ${fmtD(d.decided_on)}</div><div class="p-title">${esc(d.title)}</div>`;
      h += `<div class="pills">${vPill(v)}${governs[t.id] ? pill("q", sysName(governs[t.id])) : ""}</div>`;
      h += `<p class="why">${esc(whyStation(t.id, m))}</p>`;
      if (d.summary) h += `<div class="mt-small" style="margin-top:-8px;margin-bottom:6px">${esc(d.summary)} <span class="mt-mono">${esc(d.source ?? "")}</span></div>`;
      if (rows.length) {
        h += '<div class="sec"><h3>The line it rests on</h3>';
        rows.forEach(r => {
          const st = pState(r.id, m), evs = evUpTo(r.id, m);
          const decisive = st === "expired" ? [closedSince(r.id, m)] : st === "disputed" ? [lastOf(r.id, m, "CONTRADICTS"), lastOf(r.id, m, "SUPPORTS")] : evs.length ? [evs[evs.length - 1]] : [];
          h += `<div class="card"><div class="r"><div><div class="rt" data-open-line="${esc(r.id)}">${esc(text(r.id))}</div><div class="meta">${r.hops === 1 ? "Direct reason" : `${r.hops - 1} ${r.hops === 2 ? "branch" : "branches"} deeper`} · <span class="mt-mono">${esc(r.id)}</span></div></div>${sPill(st)}</div>` +
            ((decisive.filter(Boolean) as Ev[]).map(evHtml).join("") || '<div class="mt-evi mt-small">No dated evidence either way.</div>') + "</div>";
        });
        h += "</div>";
      }
      const sp = supersedes.filter(x => x.src === t.id || x.dst === t.id);
      if (sp.length) h += `<div class="sec"><h3>Transfer</h3><ul class="mt-list">${sp.map(x => { const o = x.src === t.id ? x.dst : x.src; return `<li data-open-st="${o}"><span>${x.src === t.id ? "Supersedes " : "Superseded by "}${esc(title(o))} <span class="mt-mono mt-small">${o}</span></span><span class="mt-small">${fmtD(x.at)}</span></li>`; }).join("")}</ul></div>`;
      const o = DATA.owners[t.id];
      if (o) h += `<div class="sec"><h3>Owner of record</h3><div>${esc(o.name)}, ${esc(o.role)}${o.active ? "" : ` <span class="mt-small">· left ${fmtD(o.valid_to)}</span>`}</div></div>`;
      const g = DATA.gate[t.id];
      if (g) h += `<div class="sec"><h3>Agent gate · ${fmtD(DATA.as_of)}</h3><div class="gate">${pill(g.action.toLowerCase(), g.action === "DENY" ? "Deny" : g.action === "ALLOW" ? "Allow" : "Revalidate")}${g.reasons.map(r => `<p>${esc(r.text)}</p>`).join("")}</div><div class="mt-small" style="margin-top:6px">check_action as of ${fmtD(DATA.as_of)}, depth 6, read-only.</div></div>`;
      h += `<div class="acts"><a class="mt-primary" data-nav href="${esc(opts.href("/app/ledger/", { d: t.id }))}">Open in the ledger</a></div>`;
    } else {
      const p = byId[t.id], st = pState(t.id, m), evs = evUpTo(t.id, m), anc = ancestors(t.id), kids = childrenOf[t.id] || [];
      h += `<div class="p-id">${esc(t.id)} · line · ${esc(p.kind)}</div><div class="p-title">${esc(p.text)}</div>`;
      h += `<div class="pills">${sPill(st)}${pill("q", `${restsOn[t.id] ? restsOn[t.id].size : 0} rules rest on it`)}</div>`;
      let why: string;
      const c = closedSince(t.id, m), lc = lastOf(t.id, m, "CONTRADICTS"), ls = lastOf(t.id, m, "SUPPORTS");
      if (st == null) why = `Not in use yet: no decision rests on it in ${fmtMonth(MONTHS[m])}.`;
      else if (st === "expired" && c) why = `Closed since ${fmtLong(c.at)}, contradicted by “${title(c.id)}” (${c.id}). Its stations stay on the map: the rules are still enforced, their line no longer runs.`;
      else if (st === "disputed" && lc && ls && ls.at >= lc.at) why = `Contradicted on ${fmtLong(lc.at)} and re-affirmed on ${fmtLong(ls.at)}. The line still runs until the owner rules.`;
      else if (st === "disputed" && lc) why = `Flagged on ${fmtLong(lc.at)} by a licence or vulnerability check that no stated reason depends on. The line still runs until the owner rules.`;
      else if (st === "holds" && ls) why = `Running. Last inspected on ${fmtLong(ls.at)}.`;
      else why = "Unsurveyed: nobody has recorded dated evidence for or against it.";
      h += `<p class="why">${esc(why)}</p>`;
      if (anc.length) h += `<div class="sec"><h3>Branches off</h3><ul class="mt-list">${anc.map(a => `<li data-open-line="${a}"><span>${esc(text(a))}</span>${sPill(pState(a, m))}</li>`).join("")}</ul></div>`;
      if (kids.length) h += `<div class="sec"><h3>Lines that branch off it</h3><ul class="mt-list">${kids.map(a => `<li data-open-line="${a}"><span>${esc(text(a))}</span>${sPill(pState(a, m))}</li>`).join("")}</ul></div>`;
      const sts = [...(restsOn[t.id] || [])].sort();
      h += `<div class="sec"><h3>Stations that rest on it</h3><ul class="mt-list">${sts.map(d => `<li data-open-st="${d}"><span>${esc(title(d))} <span class="mt-mono mt-small">${d}</span></span>${vPill(verdict(d, m))}</li>`).join("")}</ul></div>`;
      h += `<div class="sec"><h3>Inspections and breaks</h3>${evs.length ? `<div class="card">${evs.map(evHtml).join("").replace('<div class="mt-evi">', '<div class="mt-evi" style="margin-top:0;padding-top:0;border-top:0">')}</div>` : `<div class="mt-small">None recorded by ${fmtLong(MONTHS[m])}.</div>`}</div>`;
      h += '<div class="acts">';
      if (st !== "expired" && st != null) h += `<button class="mt-primary" type="button" data-r="whatifBtn">${preview?.p === t.id ? "End preview" : "What if it broke?"}</button>`;
      h += `<a class="mt-secondary" data-nav href="${esc(opts.href("/app/whatif/", { premise: t.id }))}">Open in What-if</a></div>`;
    }
    P.innerHTML = h; P.hidden = false; P.scrollTop = 0; mapEl.classList.add("has-panel");
    P.querySelector<HTMLElement>(".x")!.onclick = clearAll;
    P.querySelectorAll<HTMLElement>("[data-open-line]").forEach(e => { e.onclick = () => select({ kind: "line", id: e.dataset.openLine! }, true); });
    P.querySelectorAll<HTMLElement>("[data-open-st]").forEach(e => { e.onclick = () => select({ kind: "st", id: e.dataset.openSt! }, true); });
    const w = P.querySelector<HTMLButtonElement>('[data-r="whatifBtn"]');
    if (w) w.onclick = async () => {
      if (preview?.p === t.id) { endPreview(); openPanel(t); return; }
      w.disabled = true; w.textContent = "Testing…";
      await startPreview(t.id);
      if (alive && selected && same(selected, t)) openPanel(t);
    };
  }
  async function startPreview(p: string) {
    const B = $("whatif");
    let r: WhatIfResponse;
    try { r = await opts.whatIf(p, MONTHS[month]); }
    catch (e) { B.innerHTML = `<div>Could not test it: ${esc((e as Error).message)}</div><button class="mt-btn" type="button" data-r="endPrev">Close</button>`; B.hidden = false; $("endPrev").onclick = () => endPreview(); return; }
    if (!alive) return;
    const flips = new Set((r.decisions ?? []).filter(d => d.flips).map(d => d.id));
    preview = { p, flips, would: r.would_fall ?? flips.size, already: r.already_moot ?? 0 };
    B.innerHTML = `<div>What if <span class="q">“${esc(text(p))}”</span> broke? <b>${preview.would} more ${preview.would === 1 ? "station" : "stations"}</b> would be on a closed line${preview.already ? ` (${preview.already} already ${preview.already === 1 ? "is" : "are"})` : ""}.</div><button class="mt-btn" type="button" data-r="endPrev">End preview</button>`;
    B.hidden = false; $("endPrev").onclick = () => { endPreview(); if (selected) openPanel(selected); };
    render();
  }
  function endPreview(silent = false) { preview = null; $("whatif").hidden = true; if (!silent) render(); }

  /* ---------------- index list: the same rows as a list, for phones and screen readers ---------------- */
  function buildIndex() {
    const m = month, groups: [string, string][] = [["MOOT", "On closed lines"], ["DISPUTED", "Disputed"], ["UNDOCUMENTED", "No reason on record"], ["HOLDS", "Holding"], ["RETIRED", "Retired"]];
    let h = `<h2>Stations by verdict</h2><div class="mt-small">${fmtLong(MONTHS[m])}. The same rows as the map, as a list.</div>`;
    groups.forEach(([v, name]) => {
      const ds = decisions.filter(d => verdict(d.id, m) === v); if (!ds.length) return;
      h += `<div class="grp"><h3>${name} · ${ds.length}</h3><ul>${ds.map(d => { const r = (DATA.paths[d.id] || [])[0];
        return `<li><button type="button" data-open-st="${d.id}"><span class="t">${esc(d.title)} <span class="mt-mono mt-small">${d.id}</span></span>${r ? `<span class="s">${esc(text(r.id))}</span>` : ""}</button></li>`; }).join("")}</ul></div>`;
    });
    const I = $("index"); I.innerHTML = h;
    I.querySelectorAll<HTMLElement>("[data-open-st]").forEach(e => { e.onclick = () => { mapEl.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center" }); select({ kind: "st", id: e.dataset.openSt! }, true); }; });
  }

  /* ---------------- time ---------------- */
  function setMonth(m: number, fromPlay = false) {
    const prev = month; month = Math.max(0, Math.min(LAST, m));
    if (preview) endPreview(true); // a what-if answer is for one date
    render(); if (selected) openPanel(selected); buildIndex();
    if (fromPlay && !reduceMotion && month === prev + 1) {
      decisions.forEach(d => {
        if (verdict(d.id, prev) != null || verdict(d.id, month) == null) return;
        const R = REF.stations[d.id]; if (!R) return;
        const c = mk("circle", { cx: R.s.x, cy: R.s.y, r: R.s.r, fill: "none", stroke: theme.ink3, "stroke-width": 1.5, class: "mt-pulse" }, R.g);
        later(() => c.remove(), 1200);
      });
    }
  }
  function stop() { if (playTimer) clearInterval(playTimer); playTimer = null; $("playIcon").innerHTML = '<path d="M2 1 L11 6 L2 11 Z"/>'; $("play").setAttribute("aria-label", "Play the months"); }
  function play() {
    if (playTimer) { stop(); return; }
    if (month === LAST) setMonth(0);
    $("playIcon").innerHTML = '<rect x="2" y="1" width="3" height="10"/><rect x="7" y="1" width="3" height="10"/>'; $("play").setAttribute("aria-label", "Pause");
    playTimer = setInterval(() => { if (month >= LAST) { stop(); return; } setMonth(month + 1, true); }, 850);
  }
  $("play").addEventListener("click", play, sig);
  range.addEventListener("input", () => { stop(); setMonth(+range.value); }, sig);

  /* ---------------- search ---------------- */
  const SEARCH = [...decisions.map(d => ({ kind: "st" as const, id: d.id, label: d.title ?? d.id, k: "Station" })), ...premises.map(p => ({ kind: "line" as const, id: p.id, label: p.text ?? p.id, k: "Line" }))];
  let res: typeof SEARCH = [], resI = 0;
  const qEl = $<HTMLInputElement>("q"), rEl = $("results");
  function doSearch() {
    const q = qEl.value.trim().toLowerCase(); if (!q) { rEl.hidden = true; res = []; return; }
    res = SEARCH.filter(s => s.label.toLowerCase().includes(q) || s.id.toLowerCase().includes(q)).slice(0, 9); resI = 0;
    rEl.innerHTML = res.length ? res.map((r, i) => `<button type="button" role="option" aria-selected="${i === resI}" data-i="${i}"><span class="k">${r.k}</span><span>${esc(r.label)} <span class="mt-mono" style="color:var(--m-ink-3)">${esc(r.id)}</span></span></button>`).join("") : '<div class="mt-small" style="padding:8px">No station or line matches.</div>';
    rEl.hidden = false;
    rEl.querySelectorAll<HTMLElement>("button").forEach(b => { b.onclick = () => pick(+b.dataset.i!); });
  }
  function pick(i: number) { const r = res[i]; if (!r) return; rEl.hidden = true; qEl.blur(); select({ kind: r.kind, id: r.id }, true); }
  qEl.addEventListener("input", doSearch, sig);
  qEl.addEventListener("keydown", e => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); if (!res.length) return; resI = (resI + (e.key === "ArrowDown" ? 1 : res.length - 1)) % res.length; rEl.querySelectorAll("button").forEach((b, i) => b.setAttribute("aria-selected", String(i === resI))); }
    else if (e.key === "Enter") { e.preventDefault(); pick(resI); }
    else if (e.key === "Escape") { qEl.value = ""; rEl.hidden = true; qEl.blur(); }
  }, sig);
  document.addEventListener("keydown", e => {
    const t = e.target as Element | null, typing = !!t?.closest?.("input,textarea,select,[contenteditable]");
    if (e.key === "/" && !typing) { e.preventDefault(); qEl.focus(); qEl.select(); }
    else if (e.key === "Escape" && document.activeElement !== qEl) { if ($<HTMLDialogElement>("queries").open || document.querySelector("[role=dialog]")) return; clearAll(); }
    else if ((e.key === "ArrowRight" || e.key === "ArrowLeft") && !typing && !t?.closest?.("button,a")) { stop(); setMonth(month + (e.key === "ArrowRight" ? 1 : -1)); }
  }, sig);
  document.addEventListener("click", e => { if (!(e.target as Element | null)?.closest?.(".mt-search")) rEl.hidden = true; }, sig);
  // links in the panel go through the app router
  root.addEventListener("click", e => {
    const a = (e.target as Element | null)?.closest?.("a[data-nav]") as HTMLAnchorElement | null;
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault(); opts.navigate(a.getAttribute("href")!);
  }, sig);

  /* ---------------- queries ---------------- */
  const openQueries = () => { $("qbody").innerHTML = Object.entries(DATA.queries).map(([k, q]) => `<h3>${esc(k)}</h3><pre>${esc(q)}</pre>`).join(""); $<HTMLDialogElement>("queries").showModal(); };
  $("queriesBtn").addEventListener("click", openQueries, sig); $("queriesBtn2").addEventListener("click", openQueries, sig);

  /* ---------------- theme: follows the app's toggle and the OS ---------------- */
  const setTheme = () => { readTheme(); buildKey(); render(); };
  const mo = new MutationObserver(setTheme);
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (!document.documentElement.dataset.theme) setTheme(); }, sig);

  /* ---------------- boot ---------------- */
  function boot() {
    if (!alive) return;
    readTheme(); build(); buildTimeline(); buildKey(); render(); buildIndex(); fitAll(0);
    requestAnimationFrame(() => root.classList.add("trans"));
    if (window.innerWidth < 760) $<HTMLDetailsElement>("key").open = false;
    let rt: ReturnType<typeof setTimeout> | null = null, lastMode = MODE, lastW = mapEl.clientWidth;
    window.addEventListener("resize", () => {
      if (rt) { clearTimeout(rt); timers.delete(rt); }
      rt = later(() => {
        const nm = mapEl.clientWidth < 700 ? "narrow" : "wide";
        if (nm !== lastMode) { lastMode = nm; build(); render(); }
        if (Math.abs(mapEl.clientWidth - lastW) > 40) { lastW = mapEl.clientWidth; fitAll(0); }
      }, 180);
    }, sig);
    if (opts.initial && LAY.stations[opts.initial]) select({ kind: "st", id: opts.initial }, true);
    Object.assign(root, { __metro: { setMonth, select, clearAll, startPreview, view, layout: () => LAY } });
  }
  const fonts = document.fonts?.load
    ? Promise.all([`italic 400 12.5px ${SERIF}`, `400 23px ${SERIF}`, `550 13px ${SANS}`].map(f => document.fonts.load(f).catch(() => null))).then(() => document.fonts.ready)
    : Promise.resolve();
  Promise.race([fonts, new Promise(r => later(() => r(null), 2500))]).then(boot);

  return () => {
    alive = false; ac.abort(); mo.disconnect(); stop(); cancelAnimationFrame(raf);
    timers.forEach(t => clearTimeout(t)); timers.clear();
    root.innerHTML = ""; root.classList.remove("trans");
  };
}
