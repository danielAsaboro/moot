const $ = (s) => document.querySelector(s);
const state = { asOf: null, depth: 4, selected: null, ledger: [] };

function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 2200); }
function params() { const p = new URLSearchParams(); if (state.asOf) p.set("as_of", state.asOf); p.set("depth", state.depth); return p.toString(); }
async function api(path, opts) { const r = await fetch(path, opts); if (!r.ok) throw new Error((await r.json()).detail || r.statusText); return r.json(); }

async function loadLedger() {
  const data = await api(`/api/ledger?${params()}`);
  state.ledger = data.decisions;
  const counts = {};
  for (const d of data.decisions) counts[d.verdict] = (counts[d.verdict] || 0) + 1;
  $("#summary").innerHTML = ["MOOT", "DISPUTED", "UNDOCUMENTED", "HOLDS", "RETIRED"].filter(v => counts[v])
    .map(v => `<span><b>${counts[v]}</b> <span class="badge ${v}">${v}</span></span>`).join("") + `<span class="muted">as of ${esc(data.as_of)}, depth ${data.depth}</span>`;
  $("#ledger").innerHTML = data.decisions.map(d => `
    <tr data-id="${esc(d.id)}" class="${state.selected === d.id ? "active" : ""}">
      <td class="id">${esc(d.id)}</td>
      <td><div>${esc(d.title)}</div><div class="muted">${esc(d.owner || "no owner")}${d.owner_active ? "" : " (left)"} · ${esc((d.systems || []).join(", "))}</div></td>
      <td><span class="badge ${esc(d.verdict)}">${esc(d.verdict)}</span></td>
    </tr>`).join("");
  document.querySelectorAll("#ledger tr").forEach(tr => tr.addEventListener("click", () => openDecision(tr.dataset.id)));
}

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
    ${p.evidence.map(e => `<div class="ev"><span class="d">${esc(e.at)}</span><span><span class="rel ${esc(e.rel)}">${esc(e.rel)}</span> <span class="id">${esc(e.id)}</span> ${esc(e.title)}</span></div>`).join("")}
    ${p.evidence.length ? "" : '<div class="muted">No dated evidence touches this premise.</div>'}
    ${p.contradicted_before_decision ? '<div class="muted">The contradiction predates the decision: the premise was already false when it was made.</div>' : ""}
  </div>`;
}

function depthRow() {
  return `<div class="depthrow"><span class="muted">Depth</span>${[1,2,3,4].map(d => `<button class="ghost ${state.depth === d ? "on" : ""}" data-depth="${d}">${d}</button>`).join("")}<span class="muted">as of ${esc(state.asOf || "today")}</span></div>`;
}

function renderDecision(data, ask) {
  const a = data.audit, d = a.decision;
  const owner = a.owner ? `${esc(a.owner.name)}${a.owner.active ? "" : ` <span class="badge MOOT">left ${esc(a.owner.valid_to)}</span>`}` : "nobody";
  const others = data.impact.flatMap(i => i.decisions.filter(x => x.id !== d.id).map(x => ({...x, premise: i.premise.text})));
  const mem = data.findings && data.findings.length ? data.findings[0] : null;
  $("#panel").innerHTML = `
    ${ask ? `<div class="card"><div class="outcome">${esc(ask.outcome.replace(/_/g, " "))}${ask.narration === "model" ? " · narrated by model, citations validated" : " · template narration"}</div>
      <div class="prose">${esc(ask.answer).replace(/\[([A-Za-z0-9:_\-]+)\]/g, '<span class="cite">$1</span>')}</div></div>` : ""}
    <div class="card">
      <div class="id">${esc(d.id)} · decided ${esc(d.decided_on)} · ${esc((a.systems || []).join(", "))}</div>
      <div class="title">${esc(d.title)}</div>
      <div class="verdictline"><span class="badge fill ${esc(a.verdict)}">${esc(a.verdict)}</span><span class="muted">owner: ${owner}</span></div>
      <div class="muted">${esc(d.summary)}</div>
      ${depthRow()}
      ${a.superseded_by ? `<div class="muted">Superseded by ${esc(a.superseded_by.id)}: ${esc(a.superseded_by.title)}</div>` : ""}
      ${a.premises.length ? `<h3>Premises</h3>${a.premises.map(premiseHtml).join("")}` : `<h3>Premises</h3><div class="muted">None recorded. The ADR gives no reason, so there is nothing to check.</div>`}
      ${others.length ? `<h3>Rests on the same premise</h3>${others.map(o => `<div class="ev"><span class="id">${esc(o.id)}</span><span><a href="#" data-open="${esc(o.id)}">${esc(o.title)}</a> <span class="muted">· ${esc(o.systems.join(", "))}</span></span></div>`).join("")}` : ""}
      <h3>Moot's memory</h3>
      ${mem ? `<div class="memory">Last recorded verdict <span class="badge ${esc(mem.verdict)}">${esc(mem.verdict)}</span> as of ${esc(mem.as_of)} at depth ${esc(mem.depth)}${mem.note ? ` · ${esc(mem.note)}` : ""} <span class="muted">(${data.findings.length} finding${data.findings.length > 1 ? "s" : ""})</span></div>` : '<div class="muted">No finding recorded yet.</div>'}
      ${["MOOT", "DISPUTED"].includes(a.verdict) ? `<h3>Draft revisit ticket</h3><pre class="ticket">${esc(data.ticket)}</pre>
        <div class="row"><button class="accent" id="approve">Approve and record</button><span class="muted">Nothing is written to the graph until you approve.</span></div>` :
        `<div class="row" style="margin-top:10px"><button class="ghost" id="approve">Record this verdict</button></div>`}
    </div>`;
  document.querySelectorAll("[data-depth]").forEach(b => b.addEventListener("click", () => { state.depth = +b.dataset.depth; $("#depth").value = state.depth; loadLedger(); openDecision(d.id); }));
  document.querySelectorAll("[data-open]").forEach(x => x.addEventListener("click", e => { e.preventDefault(); openDecision(x.dataset.open); }));
  $("#approve").addEventListener("click", async () => {
    const cites = a.premises.flatMap(p => p.evidence.filter(e => e.rel === "CONTRADICTS").map(e => e.id));
    await api("/api/findings", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ decision_id: d.id, verdict: a.verdict, as_of: a.as_of, depth: a.depth, cites, note: "approved in UI" }) });
    toast(`Recorded ${a.verdict} for ${d.id} as a Finding node`);
    openDecision(d.id);
  });
}

async function openDecision(id, ask) {
  state.selected = id;
  document.querySelectorAll("#ledger tr").forEach(tr => tr.classList.toggle("active", tr.dataset.id === id));
  try {
    const data = await api(`/api/decision/${encodeURIComponent(id)}?${params()}`);
    renderDecision(data, ask);
  } catch (e) { $("#panel").innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}

$("#askForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("#q").value.trim(); if (!q) return;
  state.asOf = $("#asOf").value || null; state.depth = +$("#depth").value;
  $("#panel").innerHTML = '<div class="empty">Walking the graph…</div>';
  try {
    const r = await api("/api/ask", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question: q, as_of: state.asOf, depth: state.depth }) });
    if (r.outcome === "unknown_entity" || r.outcome === "not_in_graph") {
      $("#panel").innerHTML = `<div class="card"><div class="outcome">${esc(r.outcome.replace(/_/g, " "))}</div><div class="prose">${esc(r.answer)}</div><div class="muted" style="margin-top:8px">Moot answers only from the graph. Nothing matched, so it says so instead of guessing.</div></div>`;
      return;
    }
    await loadLedger();
    openDecision(r.audit.decision.id, r);
  } catch (err) { $("#panel").innerHTML = `<div class="empty">${esc(err.message)}</div>`; }
});
$("#asOf").addEventListener("change", () => { state.asOf = $("#asOf").value || null; loadLedger(); if (state.selected) openDecision(state.selected); });
$("#depth").addEventListener("change", () => { state.depth = +$("#depth").value; loadLedger(); if (state.selected) openDecision(state.selected); });

api("/api/health").then(h => { $("#tenant").textContent = `· ${h.tenant}`; }).catch(() => toast("FalkorDB is not reachable"));
loadLedger();
