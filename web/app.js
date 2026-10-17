const $ = (s) => document.querySelector(s);
const state = { asOf: null, depth: 4, selected: null, ledger: [], filter: "", verdictFilter: null, timeline: [], tab: "audit", lastData: null };
const VERDICTS = ["MOOT", "DISPUTED", "UNDOCUMENTED", "HOLDS", "RETIRED"];
const SAMPLES = [
  "Why do we cap uploads at 10 MB?",
  "Can we deploy on a Friday?",
  "Why are EU customers served from Frankfurt only?",
  "Do we still need manual QA sign-off?",
  "Why is the monolith off limits?",
  "Who decided to rotate API keys every 90 days?",
  "What if we no longer need SOC 2?",
  "What if the infrastructure budget changes?",
  "What is our policy on blockchain?",
];

function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 2400); }
function params() { const p = new URLSearchParams(); if (state.asOf) p.set("as_of", state.asOf); p.set("depth", state.depth); return p.toString(); }
async function api(path, opts) {
  let r;
  try { r = await fetch(path, opts); } catch (e) { banner("The Moot server is not reachable."); throw new Error("server unreachable"); }
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch (_) {}
    if (r.status === 503) banner(detail);
    throw new Error(detail);
  }
  banner(null);
  return r.json();
}
function banner(msg) { const b = $("#banner"); if (msg) { b.textContent = msg; b.hidden = false; } else b.hidden = true; }
function label(v) { return v === "NOT_YET" ? "NOT YET DECIDED" : v; }

/* ---------- rot curve: MOOT count by month end ---------- */
async function loadTimeline() {
  const data = await api(`/api/timeline?depth=${state.depth}`);
  state.timeline = data.points;
  renderTimeline();
}

function renderTimeline() {
  const pts = state.timeline; if (!pts.length) return;
  const W = 560, H = 84, pad = 4, gap = 3, n = pts.length, bw = (W - pad * 2 - gap * (n - 1)) / n;
  const max = Math.max(1, ...pts.map(p => (p.counts.MOOT || 0)));
  const sel = state.asOf ? pts.findIndex(p => p.as_of.slice(0, 7) === state.asOf.slice(0, 7)) : n - 1;
  let bars = "";
  pts.forEach((p, i) => {
    const m = p.counts.MOOT || 0, h = Math.max(2, (m / max) * (H - 26));
    const x = pad + i * (bw + gap), y = H - 16 - h;
    const nm = p.newly_moot || [];
    bars += `<rect class="bar ${m ? "moot" : ""} ${i === sel ? "on" : ""}" x="${x}" y="${y}" width="${bw}" height="${h}" data-i="${i}"><title>${esc(p.as_of)}: ${m} MOOT${nm.length ? ", newly: " + nm.join(", ") : ""}</title></rect>`;
    if (m && (i === n - 1 || i === sel || nm.length)) bars += `<text class="num" x="${x + bw / 2}" y="${y - 3}" text-anchor="middle">${m}</text>`;
    if (p.as_of.endsWith("-01-31") || i === 0) bars += `<text class="lbl" x="${x}" y="${H - 4}">${p.as_of.slice(0, 4)}</text>`;
  });
  const cur = pts[sel] || pts[n - 1];
  const first = pts.find(p => (p.counts.MOOT || 0) > 0);
  $("#rot").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="MOOT decisions by month">${bars}</svg>
    <div class="cap"><span><b>${cur.counts.MOOT || 0}</b> MOOT by ${esc(cur.as_of)}${(cur.newly_moot || []).length ? ` · newly: ${esc(cur.newly_moot.join(", "))}` : ""}</span>
    <span class="muted">${first ? `first expiry ${esc(first.as_of)}` : ""} · click a month to travel</span></div>`;
  document.querySelectorAll("#rot .bar").forEach(b => b.addEventListener("click", () => {
    const p = pts[+b.dataset.i];
    const today = new Date().toISOString().slice(0, 10);
    state.asOf = p.as_of >= today ? null : p.as_of;
    $("#asOf").value = state.asOf || "";
    refresh();
  }));
}

/* ---------- ledger ---------- */
async function loadLedger() {
  const data = await api(`/api/ledger?${params()}`);
  state.ledger = data.decisions;
  const counts = {};
  for (const d of data.decisions) counts[d.verdict] = (counts[d.verdict] || 0) + 1;
  $("#summary").innerHTML = VERDICTS.filter(v => counts[v])
    .map(v => `<span class="f ${state.verdictFilter === v ? "on" : ""}" data-v="${v}" title="Filter"><b>${counts[v]}</b> <span class="badge ${v}">${v}</span></span>`).join("")
    + `<span class="muted">as of ${esc(data.as_of)}, depth ${data.depth}</span>`;
  document.querySelectorAll("#summary .f").forEach(x => x.addEventListener("click", () => { state.verdictFilter = state.verdictFilter === x.dataset.v ? null : x.dataset.v; loadLedger(); }));
  renderLedger();
}

function renderLedger() {
  const f = state.filter.toLowerCase();
  const rows = state.ledger.filter(d => (!state.verdictFilter || d.verdict === state.verdictFilter) &&
    (!f || `${d.id} ${d.title} ${d.owner || ""} ${(d.systems || []).join(" ")}`.toLowerCase().includes(f)));
  $("#filterInfo").textContent = rows.length === state.ledger.length ? `${rows.length} decisions` : `${rows.length} of ${state.ledger.length}`;
  $("#ledger").innerHTML = rows.length ? rows.map(d => `
    <tr data-id="${esc(d.id)}" class="${state.selected === d.id ? "active" : ""}" tabindex="0">
      <td class="id">${esc(d.id)}</td>
      <td><div>${esc(d.title)}</div><div class="muted">${esc(d.owner || "no owner")}${d.owner_active ? "" : " (left)"} · ${esc((d.systems || []).join(", "))}</div></td>
      <td class="verdictcell"><span class="badge ${esc(d.verdict)}">${esc(d.verdict)}</span></td>
    </tr>`).join("") : `<tr><td class="muted" style="padding:16px 6px">Nothing matches${state.asOf ? " as of " + esc(state.asOf) : ""}.</td></tr>`;
  document.querySelectorAll("#ledger tr[data-id]").forEach(tr => {
    tr.addEventListener("click", () => openDecision(tr.dataset.id));
    tr.addEventListener("keydown", e => { if (e.key === "Enter") openDecision(tr.dataset.id); });
  });
}

/* ---------- path chain (per premise) ---------- */
function pathHtml(path, evidence) {
  const nodes = path.map(n => `<div class="node ${esc(n.label)}"><div class="lbl">${esc(n.label)}</div>${esc(n.title)}</div>`);
  let html = nodes.join('<span class="arrow">→</span>');
  const contra = [...evidence].filter(e => e.rel === "CONTRADICTS").pop();
  const sup = [...evidence].filter(e => e.rel === "SUPPORTS").pop();
  const last = contra && (!sup || sup.at < contra.at) ? contra : (sup || contra);
  if (last) html += `<span class="arrow">←</span><div class="node Evidence ${last.rel === "CONTRADICTS" ? "contra" : "sup"}"><div class="lbl">${esc(last.rel)} ${esc(last.at)}</div>${esc(last.title)}</div>`;
  return `<div class="path">${html}</div>`;
}

function premiseHtml(p) {
  return `<div class="premise">
    <div class="row"><span class="state ${esc(p.state)}">${esc(p.state)}</span><span class="muted">${p.hops} hop${p.hops > 1 ? "s" : ""}</span></div>
    <div>${esc(p.text)}</div>
    ${pathHtml(p.path, p.evidence)}
    ${p.evidence.map(e => `<div class="ev"><span class="d">${esc(e.at)}</span><span><span class="rel ${esc(e.rel)}">${esc(e.rel)}</span> <span class="id link" data-trace="${esc(e.id)}" title="What else does this document reach?">${esc(e.id)}</span> ${esc(e.title)}</span></div>`).join("")}
    ${p.evidence.length ? "" : '<div class="muted">No dated evidence touches this premise.</div>'}
    ${p.contradicted_before_decision ? '<div class="muted">The contradiction predates the decision: the premise was already false when it was made.</div>' : ""}
  </div>`;
}

/* ---------- subgraph: a layered drawing of the audit rows (no force layout, by design) ---------- */
function subgraphSvg(a) {
  const W = 760, colW = 280, nodeW = 184, nodeH = 56, vgap = 18;
  const maxHops = Math.max(1, ...a.premises.map(p => p.hops));
  const cols = []; // 0 = decision, 1..maxHops = premises by hop, maxHops+1 = evidence
  cols[0] = [{ id: a.decision.id, label: "Decision", title: a.decision.title, cls: "Decision" }];
  for (let h = 1; h <= maxHops; h++) cols[h] = [];
  cols[maxHops + 1] = [];
  const edges = [];
  const seen = new Set([a.decision.id]);
  for (const p of a.premises) {
    p.path.forEach((n, i) => {
      if (i === 0) return;
      if (!seen.has(n.id)) { seen.add(n.id); const st = n.id === p.id ? p.state : (a.premises.find(x => x.id === n.id) || {}).state; cols[i].push({ id: n.id, label: "Premise", title: n.title, cls: `Premise ${st || ""}` }); }
      edges.push({ from: p.path[i - 1].id, to: n.id, rel: i === 1 ? "BECAUSE_OF" : "DERIVED_FROM" });
    });
    for (const e of p.evidence) {
      if (!seen.has(e.id)) { seen.add(e.id); cols[maxHops + 1].push({ id: e.id, label: e.rel === "CONTRADICTS" ? "contradicts" : "supports", title: e.title, cls: `Evidence ${e.rel === "CONTRADICTS" ? "contra" : "sup"}`, at: e.at }); }
      edges.push({ from: e.id, to: p.id, rel: e.rel, at: e.at, hot: e.rel === "CONTRADICTS" && p.state === "expired" });
    }
  }
  const pos = {};
  const H = Math.max(2, ...cols.map(c => c.length)) * (nodeH + vgap) + 24;
  const scale = Math.min(1, W / ((cols.length - 1) * colW + nodeW + 20));
  cols.forEach((col, ci) => col.forEach((n, ri) => {
    const total = col.length * (nodeH + vgap) - vgap;
    pos[n.id] = { x: 10 + ci * colW, y: (H - total) / 2 + ri * (nodeH + vgap), n };
  }));
  const trunc = (s, n) => s.length > n ? s.slice(0, n - 1) + "…" : s;
  let out = "";
  for (const e of edges) {
    const f = pos[e.from], t = pos[e.to]; if (!f || !t) continue;
    const x1 = f.x + nodeW, y1 = f.y + nodeH / 2, x2 = t.x, y2 = t.y + nodeH / 2;
    const left = f.x > t.x; // evidence points back at premise
    const sx = left ? f.x : x1, ex = left ? t.x + nodeW : x2, mx = (sx + ex) / 2;
    out += `<path class="e ${e.hot ? "hot" : ""} ${e.rel === "SUPPORTS" ? "sup" : ""}" d="M${sx},${y1} C${mx},${y1} ${mx},${y2} ${ex},${y2}"/>`;
    out += `<text class="el" x="${mx}" y="${(y1 + y2) / 2 - 4}" text-anchor="middle">${esc(e.rel)}</text>`;
  }
  for (const id in pos) {
    const { x, y, n } = pos[id];
    const words = n.title.split(" "), lines = [""];
    for (const w of words) { if ((lines[lines.length - 1] + " " + w).trim().length > 27 && lines.length < 2) lines.push(w); else lines[lines.length - 1] = (lines[lines.length - 1] + " " + w).trim(); }
    if (lines.length === 2 && lines[1].length > 27) lines[1] = trunc(lines[1], 27);
    out += `<g class="n ${esc(n.cls)}" transform="translate(${x},${y})"><rect width="${nodeW}" height="${nodeH}"/>
      <text class="k ${n.cls.includes("contra") ? "contra" : n.cls.includes("sup") ? "sup" : ""}" x="8" y="14">${esc(n.label.toUpperCase())} ${esc(n.id)}${n.at ? " · " + esc(n.at) : ""}</text>
      <text x="8" y="31">${esc(lines[0])}</text><text x="8" y="46">${esc(lines[1] || "")}</text></g>`;
  }
  const vw = (cols.length - 1) * colW + nodeW + 20;
  return `<div class="sub"><svg viewBox="0 0 ${vw} ${H}" style="max-height:${Math.round(H * scale) + 20}px">${out}</svg>
    <div class="legend">Left to right: the decision, its premises by hop, then the dated evidence that touches them. The red edge is the contradiction that decides the verdict.</div></div>`;
}

/* ---------- cypher view ---------- */
function cypherHtml(queries) {
  if (!queries || !queries.length) return '<div class="muted">No queries recorded.</div>';
  const total = queries.reduce((s, q) => s + q.ms, 0);
  const kw = s => esc(s).replace(/\b(MATCH|OPTIONAL MATCH|WHERE|RETURN|WITH|ORDER BY|LIMIT|CALL|YIELD|UNWIND|CREATE|FOREACH|DISTINCT|AS|collect|length|nodes|type)\b/g, '<span class="kw">$1</span>');
  return `<div class="cy"><div class="total">${queries.length} read-only Cypher quer${queries.length > 1 ? "ies" : "y"} against FalkorDB, ${total.toFixed(1)} ms in the database. The model never sees them.</div>
    ${queries.map((q, i) => `<div class="q"><div class="meta"><span>#${i + 1}</span><span>${q.rows} row${q.rows === 1 ? "" : "s"}</span><span>${q.ms} ms</span><span>${esc(JSON.stringify(q.params))}</span></div><pre>${kw(q.cypher.replace(/ (OPTIONAL MATCH|MATCH|WHERE|RETURN|WITH|ORDER BY|CALL) /g, "\n$1 "))}</pre></div>`).join("")}</div>`;
}

function depthRow() {
  return `<div class="depthrow"><span class="muted">Depth</span>${[1,2,3,4].map(d => `<button class="ghost ${state.depth === d ? "on" : ""}" data-depth="${d}">${d}</button>`).join("")}<span class="muted">as of ${esc(state.asOf || "today")}</span></div>`;
}

/* ---------- decision panel ---------- */
function renderDecision(data, ask) {
  const a = data.audit, d = a.decision;
  state.lastData = data;
  const owner = a.owner ? `${esc(a.owner.name)}${a.owner.active ? "" : ` <span class="badge MOOT">left ${esc(a.owner.valid_to)}</span>`}` : "nobody";
  const others = data.impact.flatMap(i => i.decisions.filter(x => x.id !== d.id).map(x => ({...x, premise: i.premise.text})));
  const mem = data.findings && data.findings.length ? data.findings[0] : null;
  const queries = (ask && ask.queries) || data.queries;
  const notYet = a.verdict === "NOT_YET";
  $("#panel").innerHTML = `
    ${ask ? `<div class="card"><div class="outcome">${esc(ask.outcome.replace(/_/g, " "))}${ask.narration === "model" ? " · narrated by model, citations validated" : " · template narration"}</div>
      <div class="prose">${esc(ask.answer).replace(/\[([A-Za-z0-9:_\-]+)\]/g, '<span class="cite">$1</span>')}</div></div>` : ""}
    <div class="card">
      <div class="id">${esc(d.id)} · decided ${esc(d.decided_on)} · ${esc((a.systems || []).join(", "))}</div>
      <div class="title">${esc(d.title)}</div>
      <div class="verdictline"><span class="badge fill ${esc(a.verdict)}">${esc(label(a.verdict))}</span><span class="muted">owner: ${owner}</span></div>
      <div class="muted">${esc(d.summary)}</div>
      <details class="doc" id="adrBox"><summary>Read the ADR <span class="muted">· ${esc(d.source || "")}</span></summary><pre class="ticket">Loading…</pre></details>
      ${depthRow()}
      ${notYet ? `<div class="notyet">As of ${esc(a.as_of)} this decision had not been made yet. Move the date forward.</div>` : `
      <div class="tabs">${[["audit", "Audit"], ["graph", "Graph"], ["cypher", "Cypher"]].map(([k, t]) => `<button class="${state.tab === k ? "on" : ""}" data-tab="${k}">${t}</button>`).join("")}</div>
      <div class="tab ${state.tab === "audit" ? "on" : ""}" data-pane="audit">
        ${a.superseded_by ? `<div class="muted" style="margin-top:10px">Superseded by <a href="#" data-open="${esc(a.superseded_by.id)}">${esc(a.superseded_by.id)}: ${esc(a.superseded_by.title)}</a></div>` : ""}
        ${a.premises.length ? `<h3>Premises</h3>${a.premises.map(premiseHtml).join("")}` : `<h3>Premises</h3><div class="muted">None recorded. The ADR gives no reason, so there is nothing to check.</div>`}
        ${others.length ? `<h3>Rests on the same premise</h3>${others.map(o => `<div class="ev"><span class="id">${esc(o.id)}</span><span><a href="#" data-open="${esc(o.id)}">${esc(o.title)}</a> <span class="muted">· ${esc(o.systems.join(", "))}</span></span></div>`).join("")}` : ""}
        <div id="traceBox"></div>
        <h3>Moot's memory</h3>
        ${mem ? `<div class="memory">${mem.kind === "reopen" ? "Re-opened" : "Last recorded verdict"} <span class="badge ${esc(mem.verdict)}">${esc(mem.verdict)}</span> as of ${esc(mem.as_of)} at depth ${esc(mem.depth)}${mem.assignee ? ` · follow-up owned by <b>${esc(mem.assignee)}</b>` : ""}${mem.kind !== "reopen" && mem.note ? ` · ${esc(mem.note)}` : ""} <span class="muted">(${data.findings.length} finding${data.findings.length > 1 ? "s" : ""})</span></div>` : '<div class="muted">No finding recorded yet.</div>'}
        ${data.memo && data.memo.broken.length ? memoHtml(data.memo) :
          `<div class="row" style="margin-top:10px"><button class="ghost" id="approve">Record this verdict</button></div>`}
      </div>
      <div class="tab ${state.tab === "graph" ? "on" : ""}" data-pane="graph">${a.premises.length ? subgraphSvg(a) : '<div class="muted" style="margin-top:10px">No premises, so no path to draw.</div>'}</div>
      <div class="tab ${state.tab === "cypher" ? "on" : ""}" data-pane="cypher">${cypherHtml(queries)}</div>`}
    </div>`;
  document.querySelectorAll("[data-tab]").forEach(b => b.addEventListener("click", () => {
    state.tab = b.dataset.tab;
    document.querySelectorAll("[data-tab]").forEach(x => x.classList.toggle("on", x.dataset.tab === state.tab));
    document.querySelectorAll("[data-pane]").forEach(x => x.classList.toggle("on", x.dataset.pane === state.tab));
  }));
  document.querySelectorAll("[data-depth]").forEach(b => b.addEventListener("click", () => { state.depth = +b.dataset.depth; $("#depth").value = state.depth; refresh(); }));
  document.querySelectorAll("[data-open]").forEach(x => x.addEventListener("click", e => { e.preventDefault(); openDecision(x.dataset.open); }));
  document.querySelectorAll("[data-trace]").forEach(x => x.addEventListener("click", () => traceDoc(x.dataset.trace)));
  const adr = $("#adrBox");
  if (adr) adr.addEventListener("toggle", async () => {
    if (!adr.open || adr.dataset.loaded) return;
    try { const doc = await api(`/api/document/src:${encodeURIComponent(d.id)}`); adr.querySelector("pre").textContent = doc.text; adr.dataset.loaded = "1"; }
    catch (e) { adr.querySelector("pre").textContent = e.message; }
  }, { once: false });
  const cp = $("#copyTicket");
  if (cp) cp.addEventListener("click", async () => { try { await navigator.clipboard.writeText(data.ticket); toast("Memo copied"); } catch (_) { toast("Copy failed"); } });
  const ro = $("#approveReopen");
  if (ro) ro.addEventListener("click", async () => {
    ro.disabled = true;
    try {
      const r = await api("/api/reopen", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ decision_id: d.id, as_of: a.as_of, depth: a.depth, owner_id: data.memo.suggested_owner.id }) });
      toast(`Re-opened ${d.id}${r.assignee ? ", assigned to " + (data.memo.suggested_owner.name || r.assignee) : ""}`);
      openDecision(d.id); loadWatch();
    } catch (e) { toast(e.message); ro.disabled = false; }
  });
  const ap = $("#approve");
  if (ap) ap.addEventListener("click", async () => {
    ap.disabled = true;
    const cites = a.premises.flatMap(p => p.evidence.filter(e => e.rel === "CONTRADICTS").map(e => e.id));
    try {
      await api("/api/findings", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ decision_id: d.id, verdict: a.verdict, as_of: a.as_of, depth: a.depth, cites, note: "approved in UI" }) });
      toast(`Recorded ${a.verdict} for ${d.id} as a Finding node`);
      openDecision(d.id);
    } catch (e) { toast(e.message); ap.disabled = false; }
  });
}

/* ---------- re-open memo ---------- */
function chainHtml(path) {
  return `<div class="path">${path.map(n => `<div class="node ${esc(n.label)}"><div class="lbl">${esc(n.label)} ${esc(n.id)}</div>${esc(n.title)}</div>`).join('<span class="arrow">→</span>')}</div>`;
}

function memoHtml(m) {
  const s = m.suggested_owner;
  return `<h3>Re-open memo</h3><div class="memo">
    <div class="mrow"><div class="mk">Which reason broke</div><div>${m.broken.map(b => `<div>“${esc(b.premise.text)}” <span class="state ${esc(b.state)}">${esc(b.state)}</span>${b.hops > 1 ? `<div class="muted">The stated reason, “${esc(b.stated.text)}”, only holds because of it (${b.hops} hops).</div>` : ""}</div>`).join("")}</div></div>
    <div class="mrow"><div class="mk">New evidence</div><div>${m.broken.map(b => `<div><span class="id">${esc(b.evidence.at)}</span> <span class="id link" data-trace="${esc(b.evidence.id)}">${esc(b.evidence.id)}</span> ${esc(b.evidence.title)}${b.reaffirmed_by ? `<div class="muted">Re-affirmed ${esc(b.reaffirmed_by.at)} by ${esc(b.reaffirmed_by.id)}: disputed, not dead.</div>` : ""}</div>`).join("")}</div></div>
    <div class="mrow"><div class="mk">Also affected</div><div>${m.affected.length ? m.affected.map(x => `<div><a href="#" data-open="${esc(x.id)}">${esc(x.id)} ${esc(x.title)}</a> <span class="badge ${esc(x.verdict)}">${esc(x.verdict)}</span></div>`).join("") : '<span class="muted">No other decision rests on this reason.</span>'}</div></div>
    <div class="mrow"><div class="mk">Suggested owner</div><div><b>${esc(s.name || "unassigned")}</b>${s.role ? ` <span class="muted">${esc(s.role)}</span>` : ""}<div class="muted">${esc(s.why)}</div></div></div>
  </div>
  <details class="doc"><summary>Memo as plain text</summary><pre class="ticket">${esc(m.text)}</pre></details>
  <div class="row" style="margin-top:10px"><button class="accent" id="approveReopen">Approve: re-open${s.name ? " and assign to " + esc(s.name.split(" ")[0]) : ""}</button><button class="ghost" id="copyTicket">Copy</button><span class="muted">Nothing is written to the graph until you approve.</span></div>`;
}

/* ---------- watch strip: orphans + riskiest reasons ---------- */
async function loadWatch() {
  try {
    const [o, r] = await Promise.all([api(`/api/orphans?${params()}`), api(`/api/risky?${params()}&limit=3`)]);
    state.orphans = o; state.risky = r;
    const who = o.groups.map(g => g.person.name.split(" ")[0]).join(" and ");
    $("#watch").innerHTML = `
      <button class="wrow" id="wOrphans"><span class="wn ${o.count ? "hot" : ""}">${o.count}</span><span><b>Orphaned decision${o.count === 1 ? "" : "s"}</b><span class="muted">${o.count ? `owned by ${esc(who)}, who left` : "every live decision has an owner who is still here"}</span></span><span class="go">Hand over →</span></button>
      <button class="wrow" id="wRisky"><span class="wn">${r.reasons.length ? r.reasons[0].standing : 0}</span><span><b>Riskiest reason</b><span class="muted">${r.reasons.length ? `“${esc(r.reasons[0].text)}” carries ${r.reasons[0].standing} standing decisions` : "no shared reasons"}</span></span><span class="go">What if →</span></button>`;
    $("#wOrphans").addEventListener("click", showOrphans);
    $("#wRisky").addEventListener("click", showRisky);
  } catch (_) {}
}

function unselect() { state.selected = null; document.querySelectorAll("#ledger tr").forEach(tr => tr.classList.remove("active")); }

async function showOrphans() {
  unselect(); location.hash = "orphans";
  $("#panel").innerHTML = '<div class="empty"><div class="empty-title">Walking the reporting lines…</div></div>';
  const o = await api(`/api/orphans?${params()}`); state.orphans = o;
  $("#panel").innerHTML = `<div class="card">
    <div class="outcome">orphaned decisions · as of ${esc(o.as_of)}</div>
    <div class="title">${o.count} live decision${o.count === 1 ? "" : "s"} lost ${o.count === 1 ? "its" : "their"} owner</div>
    <div class="muted">Each one goes up the reporting line, as it stood on the day the owner left, to the first person who is still here. The reasons and verdict travel with it. Approving writes a new dated OWNS edge; the old one stays, so time travel still shows who owned it then.</div>
    ${o.groups.map(g => `<div class="leaver">
      <h3>${esc(g.person.name)} · ${esc(g.person.role)} · left ${esc(g.person.left)}</h3>
      ${g.successor ? `<div class="path">${g.successor.chain.map((n, i) => `<div class="node Person ${i && i < g.successor.chain.length - 1 ? "gone" : ""}"><div class="lbl">${i === 0 ? "left" : n.left && n.left <= o.as_of ? "also left " + esc(n.left) : "routes to"}</div>${esc(n.name)}</div>`).join('<span class="arrow">REPORTS_TO →</span>')}</div>` : '<div class="muted">Nobody in this reporting line is still here.</div>'}
      ${g.decisions.map(d => `<div class="orow">
        <div><span class="id">${esc(d.id)}</span> <a href="#" data-open="${esc(d.id)}">${esc(d.title)}</a> <span class="badge ${esc(d.verdict)}">${esc(d.verdict)}</span>
          ${d.reasons.map(r => `<div class="muted">${r.hops > 1 ? "↳ which holds only while" : "because"} “${esc(r.text)}” <span class="state ${esc(r.state)}">${esc(r.state)}</span></div>`).join("") || '<div class="muted">no reason recorded</div>'}</div>
        ${g.successor ? `<button class="accent small" data-hand="${esc(d.id)}" data-to="${esc(g.successor.id)}">Hand to ${esc(g.successor.name.split(" ")[0])}</button>` : ""}
      </div>`).join("")}
    </div>`).join("") || '<div class="muted" style="margin-top:12px">Nothing to hand over.</div>'}
  </div>`;
  bindPanelLinks();
  document.querySelectorAll("[data-hand]").forEach(b => b.addEventListener("click", async () => {
    b.disabled = true;
    try {
      const r = await api("/api/handover", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ decision_id: b.dataset.hand, to: b.dataset.to, as_of: state.asOf || new Date().toISOString().slice(0, 10) }) });
      toast(`${r.decision_id} now owned by ${r.to_name || r.to}`);
      await Promise.all([loadLedger(), loadWatch()]); showOrphans();
    } catch (e) { toast(e.message); b.disabled = false; }
  }));
}

function whatIfHtml(w) {
  const falls = w.decisions.filter(x => x.flips), already = w.decisions.filter(x => !x.flips);
  const row = x => `<div class="orow"><div><span class="id">${esc(x.id)}</span> <a href="#" data-open="${esc(x.id)}">${esc(x.title)}</a>
      <span class="flip"><span class="badge ${esc(x.before)}">${esc(x.before)}</span> → <span class="badge ${esc(x.after)}">${esc(x.after)}</span></span>
      ${chainHtml([...x.path].reverse())}<div class="muted">owner ${esc(x.owner || "none")} · ${esc(x.systems.join(", "))}</div></div></div>`;
  return `<div class="card">
    <div class="outcome">what if · as of ${esc(w.as_of)} · depth ${w.depth}</div>
    <div class="title">If “${esc(w.premise.text)}” broke today, ${w.would_fall} standing decision${w.would_fall === 1 ? "" : "s"} would fall</div>
    <div class="muted">${w.decisions.length} decision${w.decisions.length === 1 ? "" : "s"} rest on this reason, directly or through premises derived from it${w.systems.length ? ` · systems: ${esc(w.systems.join(", "))}` : ""}. Nothing is written; this is a read-only path query.</div>
    ${w.candidates && w.candidates.length > 1 ? `<div class="chips">${w.candidates.map(c => `<button class="chip ${c.id === w.premise.id ? "on" : ""}" data-whatif="${esc(c.id)}">${esc(c.text)}</button>`).join("")}</div>` : ""}
    ${falls.length ? `<h3>Would fall</h3>${falls.map(row).join("")}` : ""}
    ${already.length ? `<h3>Already ${already.every(x => x.before === "MOOT") ? "moot" : "unchanged"}</h3>${already.map(row).join("")}` : ""}
    <div id="riskyBox"></div>
    <details class="doc"><summary>Cypher</summary>${cypherHtml(w.queries)}</details>
  </div>`;
}

async function runWhatIf(q, premise) {
  unselect(); location.hash = "whatif";
  $("#panel").innerHTML = '<div class="empty"><div class="empty-title">Pretending it broke…</div></div>';
  const p = new URLSearchParams(params()); if (premise) p.set("premise", premise); else p.set("q", q);
  try {
    const w = await api(`/api/whatif?${p}`);
    if (!w.found) {
      $("#panel").innerHTML = `<div class="card"><div class="outcome">what if · not in the graph</div><div class="prose">${esc(w.answer)}</div><div id="riskyBox"></div></div>`;
    } else {
      $("#panel").innerHTML = whatIfHtml(w);
    }
    bindPanelLinks();
    document.querySelectorAll("[data-whatif]").forEach(b => b.addEventListener("click", () => runWhatIf(null, b.dataset.whatif)));
    renderRisky($("#riskyBox"), await api(`/api/risky?${params()}`));
  } catch (e) { $("#panel").innerHTML = `<div class="empty"><div class="empty-title">${esc(e.message)}</div></div>`; }
}

function renderRisky(box, r) {
  if (!box) return;
  box.innerHTML = `<h3>Riskiest reasons</h3><div class="muted" style="margin-bottom:6px">Ranked by how many standing decisions sit below each reason. If one breaks, everything under it breaks with it. Click one to test it.</div>
    <table class="risky"><tbody>${r.reasons.map(x => `<tr data-whatif="${esc(x.id)}" tabindex="0">
      <td class="id">${x.rank}</td><td><div>${esc(x.text)}</div><div class="muted">${esc(x.decision_ids.join(", "))} · ${esc(x.systems.join(", "))}</div></td>
      <td class="num"><b>${x.standing}</b><span class="muted"> / ${x.decisions}</span></td><td><span class="state ${esc(x.state)}">${esc(x.state)}</span></td></tr>`).join("")}</tbody></table>
    <div class="muted" style="margin-top:4px">standing / total decisions resting on the reason, as of ${esc(r.as_of)}</div>`;
  box.querySelectorAll("[data-whatif]").forEach(b => b.addEventListener("click", () => runWhatIf(null, b.dataset.whatif)));
}

async function showRisky() {
  unselect(); location.hash = "risky";
  const r = await api(`/api/risky?${params()}`);
  if (r.reasons.length) return runWhatIf(null, r.reasons[0].id);
  $("#panel").innerHTML = '<div class="card"><div class="muted">No reason carries a live decision.</div></div>';
}

function bindPanelLinks() {
  document.querySelectorAll("#panel [data-open]").forEach(x => x.addEventListener("click", e => { e.preventDefault(); openDecision(x.dataset.open); }));
}

async function traceDoc(id) {
  const box = $("#traceBox"); if (!box) return;
  box.innerHTML = '<div class="trace muted">Tracing shortest paths…</div>';
  try {
    const [r, doc] = await Promise.all([api(`/api/trace/${encodeURIComponent(id)}`), api(`/api/document/${encodeURIComponent(id)}`).catch(() => null)]);
    box.innerHTML = `<div class="trace"><div class="t">${esc(r.evidence.id)} reaches ${r.reaches.length} decision${r.reaches.length === 1 ? "" : "s"}</div>
      <div class="muted" style="margin-bottom:6px">${esc(r.evidence.title)} · ${esc(r.evidence.date)} · shortest paths via algo.SPpaths</div>
      ${r.reaches.map(x => `<div class="ev"><span class="id">${esc(x.id)}</span><span><a href="#" data-open="${esc(x.id)}">${esc(x.title)}</a> <span class="muted">· ${x.hops} hop${x.hops === 1 ? "" : "s"}</span></span></div>`).join("")}
      ${doc ? `<details class="doc"><summary>Source text <span class="muted">· ${esc(doc.kind)} · ${esc(doc.path)}</span></summary><pre class="ticket">${esc(doc.text)}</pre></details>` : ""}</div>`;
    box.querySelectorAll("[data-open]").forEach(x => x.addEventListener("click", e => { e.preventDefault(); openDecision(x.dataset.open); }));
  } catch (e) { box.innerHTML = `<div class="trace muted">${esc(e.message)}</div>`; }
}

async function openDecision(id, ask) {
  state.selected = id;
  document.querySelectorAll("#ledger tr").forEach(tr => tr.classList.toggle("active", tr.dataset.id === id));
  if (!ask) $("#panel").innerHTML = '<div class="card"><div class="skeleton" style="width:40%"></div><br><div class="skeleton" style="width:70%;height:24px"></div><br><div class="skeleton"></div></div>';
  try {
    const data = await api(`/api/decision/${encodeURIComponent(id)}?${params()}`);
    renderDecision(data, ask);
    location.hash = id;
  } catch (e) { $("#panel").innerHTML = `<div class="empty"><div class="empty-title">${esc(e.message)}</div></div>`; }
}

async function refresh() {
  await Promise.all([loadLedger(), loadTimeline(), loadWatch()]);
  if (state.selected) openDecision(state.selected);
  else if (location.hash === "#orphans") showOrphans();
}

/* ---------- ask ---------- */
async function askQuestion(q) {
  state.asOf = $("#asOf").value || null; state.depth = +$("#depth").value;
  if (/^\s*(what if|what happens if|if)\b/i.test(q)) return runWhatIf(q);
  $("#askBtn").disabled = true;
  $("#panel").innerHTML = '<div class="empty"><div class="empty-title">Walking the graph…</div></div>';
  try {
    const r = await api("/api/ask", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question: q, as_of: state.asOf, depth: state.depth }) });
    if (r.outcome === "unknown_entity" || r.outcome === "not_in_graph") {
      state.selected = null;
      $("#panel").innerHTML = `<div class="card"><div class="outcome">${esc(r.outcome.replace(/_/g, " "))}</div><div class="prose">${esc(r.answer)}</div><div class="muted" style="margin-top:8px">Moot answers only from the graph. Nothing matched, so it says so instead of guessing.</div>${cypherHtml(r.queries)}</div>`;
      return;
    }
    await loadLedger();
    await openDecision(r.audit.decision.id, r);
  } catch (err) { $("#panel").innerHTML = `<div class="empty"><div class="empty-title">${esc(err.message)}</div></div>`; }
  finally { $("#askBtn").disabled = false; }
}

$("#askForm").addEventListener("submit", e => { e.preventDefault(); const q = $("#q").value.trim(); if (q) askQuestion(q); });
$("#chips").innerHTML = SAMPLES.map(s => `<button type="button" class="chip">${esc(s)}</button>`).join("");
document.querySelectorAll(".chip").forEach(c => c.addEventListener("click", () => { $("#q").value = c.textContent; askQuestion(c.textContent); }));
$("#asOf").addEventListener("change", () => { state.asOf = $("#asOf").value || null; refresh(); });
$("#depth").addEventListener("change", () => { state.depth = +$("#depth").value; refresh(); });
$("#filter").addEventListener("input", e => { state.filter = e.target.value; renderLedger(); });
document.addEventListener("keydown", e => { if (e.key === "/" && document.activeElement.tagName !== "INPUT") { e.preventDefault(); $("#q").focus(); } });

/* theme */
const savedTheme = (() => { try { return localStorage.getItem("moot-theme"); } catch (_) { return null; } })();
if (savedTheme) document.documentElement.dataset.theme = savedTheme;
$("#theme").addEventListener("click", () => {
  const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const next = cur === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("moot-theme", next); } catch (_) {}
});

/* boot */
api("/api/health").then(h => {
  const n = h.stats.nodes, e = h.stats.edges;
  $("#tenant").textContent = `${h.tenant} · ${Object.values(n).reduce((a, b) => a + b, 0)} nodes · ${Object.values(e).reduce((a, b) => a + b, 0)} edges`;
  if (!h.model) document.querySelector("footer").insertAdjacentHTML("afterbegin", "No model key is set, so narration uses the template. ");
}).catch(() => {});
refresh().then(() => { const id = location.hash.slice(1); if (/^D\d{2}$/.test(id)) openDecision(id); else if (id === "risky" || id === "whatif") showRisky(); });
