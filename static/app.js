/* VitalRoute dual-persona client.
   Zero-framework vanilla JS + MapLibre GL + WebSockets + Web Audio API. */
"use strict";

const API = "";
const AMB_ID = "AMB-1";
let role = "cockpit";
let hospitals = [];
let assessment = null;          // last AssessmentResult
let handshake = null;           // active handshake (cockpit)
let hospitalSelection = "H1";   // which ER this HUD represents
let lastVitals = null, lastTag = "GENERAL";
let pos = { lat: 28.6129, lon: 77.2295 };   // default city centre
let muted = false;
let whatifOverrides = {};       // simulator counterfactual draft

/* ------------------------------------------------------------------ audio */
let actx = null;
function chime(kind = "request") {
  if (muted) return;
  actx = actx || new (window.AudioContext || window.webkitAudioContext)();
  const notes = kind === "request" ? [880, 660, 880] : kind === "ok" ? [660, 990] : [440, 330];
  notes.forEach((f, i) => {
    const o = actx.createOscillator(), g = actx.createGain();
    o.type = "sine"; o.frequency.value = f;
    g.gain.setValueAtTime(0, actx.currentTime + i * 0.18);
    g.gain.linearRampToValueAtTime(0.18, actx.currentTime + i * 0.18 + 0.02);
    g.gain.exponentialRampToValueAtTime(0.001, actx.currentTime + i * 0.18 + 0.16);
    o.connect(g).connect(actx.destination);
    o.start(actx.currentTime + i * 0.18); o.stop(actx.currentTime + i * 0.18 + 0.2);
  });
}

/* ---------------------------------------------------------------- websock */
let ws;
function connectWS() {
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/${wsChannel()}`);
  ws.onopen = () => { document.getElementById("conn").textContent = "WS: connected"; document.getElementById("conn").className = "conn ok"; };
  ws.onclose = () => { document.getElementById("conn").textContent = "WS: reconnecting…"; document.getElementById("conn").className = "conn off"; setTimeout(connectWS, 2000); };
  ws.onmessage = (e) => onWS(JSON.parse(e.data));
}
function wsChannel() {
  if (role === "cockpit") return `ambulance:${AMB_ID}`;
  if (role === "hospital") return `hospital:${hospitalSelection}`;
  return "sim";
}
function onWS(msg) {
  if (msg.type === "hospital_update") {
    const i = hospitals.findIndex(h => h.id === msg.hospital.id);
    if (i >= 0) hospitals[i] = msg.hospital; else hospitals.push(msg.hospital);
    renderMapMarkers();
    if (role === "cockpit") {
      const resEl = document.getElementById("results");
      if (resEl && assessment) resEl.innerHTML = resultsHTML();
    } else {
      renderPanel();
    }
  } else if (msg.type === "handshake_request" && role === "hospital") {
    chime("request");
    pendingRequest = msg;
    renderPanel();
  } else if (msg.type === "handshake_ack" && role === "cockpit") {
    handshake = msg.handshake;
    chime(handshake.status === "CONFIRMED" ? "ok" : "bad");
    renderPanel();
  } else if (msg.type === "handshake_timeout" && role === "cockpit") {
    handshake = msg.handshake;
    chime("bad");
    renderPanel();
  }
}


/* ------------------------------------------------------------------- map */
let map = null, markers = {}, ambMarker = null;
function initMap() {
  if (typeof maplibregl === "undefined") { document.getElementById("mapOffline").hidden = false; return; }
  try {
    map = new maplibregl.Map({
      container: "map",
      style: "https://tiles.openfreemap.org/styles/dark",
      center: [77.2295, 28.6129], zoom: 11.5,
      attributionControl: { compact: true },
    });
    map.on("error", () => document.getElementById("mapOffline").hidden = false);
    map.addControl(new maplibregl.NavigationControl());
  } catch { document.getElementById("mapOffline").hidden = false; }
}
function el(cls, html) { const d = document.createElement("div"); d.className = cls; d.innerHTML = html; return d; }
function markerEl(h) {
  const color = h.stale ? "#e5484d" : h.beds_available === 0 ? "#666" : h.freshness < 0.75 ? "#f5a524" : "#30a46c";
  return el("map-marker", `<div style="background:${color};width:14px;height:14px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 8px ${color};" title="${h.name}"></div>`);
}
function renderMapMarkers() {
  if (!map) return;
  hospitals.forEach(h => {
    if (!markers[h.id]) markers[h.id] = new maplibregl.Marker({ element: markerEl(h) }).setLngLat([h.longitude, h.latitude]).addTo(map);
    else markers[h.id].setLngLat([h.longitude, h.latitude]);
    markers[h.id].getElement().firstChild.style.background = h.stale ? "#e5484d" : (h.beds_available === 0 ? "#666" : "#30a46c");
  });
  if (!ambMarker) ambMarker = new maplibregl.Marker({ element: el("", `<div style="width:0;height:0;border-left:9px solid transparent;border-right:9px solid transparent;border-bottom:16px solid #52a8ff;filter:drop-shadow(0 0 6px #52a8ff);"></div>`) }).setLngLat([pos.lon, pos.lat]).addTo(map);
  ambMarker.setLngLat([pos.lon, pos.lat]);
}

/* ------------------------------------------------------------ geolocation */
if ("geolocation" in navigator) {
  navigator.geolocation.watchPosition(
    (p) => { pos = { lat: p.coords.latitude, lon: p.coords.longitude };
      document.getElementById("geoStatus").textContent = `GPS: ${pos.lat.toFixed(4)}, ${pos.lon.toFixed(4)}`;
      renderMapMarkers(); },
    () => { document.getElementById("geoStatus").textContent = "GPS: using simulated scene position"; },
    { enableHighAccuracy: true, maximumAge: 5000 });
} else {
  document.getElementById("geoStatus").textContent = "GPS: unavailable — simulated position";
}

/* ---------------------------------------------------------------- helpers */
const $ = (s) => document.querySelector(s);
async function api(path, opts) {
  const r = await fetch(API + path, opts && {
    method: opts.method || "POST",
    headers: { "Content-Type": "application/json" },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}
function fmtFresh(h) {
  const mins = h.staleness_minutes;
  const cls = h.stale ? "stale" : h.freshness < 0.75 ? "warn" : "ok";
  return `<span class="fresh ${cls}">F=${h.freshness.toFixed(2)} · ${mins.toFixed(0)}m ago</span>`;
}

/* =====================================================================
   VIEW: Paramedic Cockpit
===================================================================== */
function cockpitView() {
  const hsBanner = handshake ? handshakeBanner() : "";
  return `${hsBanner}
  <h2>Patient Assessment — Field Intake (30 s)</h2>
  <div class="grid2">
    <div class="field"><label>Respiration (br/min)</label><input id="rr" type="number" value="18" min="0" max="80"></div>
    <div class="field"><label>SpO₂ (%)</label><input id="spo2" type="number" value="97" min="50" max="100"></div>
    <div class="field"><label>Systolic BP (mmHg)</label><input id="sbp" type="number" value="124" min="40" max="300"></div>
    <div class="field"><label>Heart Rate (bpm)</label><input id="hr" type="number" value="88" min="20" max="250"></div>
    <div class="field"><label>Temp (°C)</label><input id="temp" type="number" step="0.1" value="37.0" min="30" max="43"></div>
    <div class="field"><label>Consciousness (AVPU)</label>
      <select id="avpu"><option>A</option><option>V</option><option>P</option><option>U</option></select></div>
  </div>
  <div class="field"><label>Field triage tag (NEWS2 + tags — ESI is assigned by the receiving hospital)</label>
    <div class="tags">
      <button data-tag="STEMI">#STEMI</button>
      <button data-tag="STROKE">#STROKE</button>
      <button data-tag="TRAUMA">#TRAUMA</button>
      <button data-tag="GENERAL" class="active">#GENERAL</button>
    </div></div>
  <button class="btn" id="btnRank">Compute Ranked Destinations</button>
  <div id="results">${assessment ? resultsHTML() : `<p class="rationale" style="margin-top:14px">Enter vitals, pick a care tag, and run the TTDC optimizer.</p>`}</div>`;
}

function handshakeBanner() {
  const map = {
    PENDING_RESPONSE: ["pending", `Handshake PENDING with ${handshake.hospital_id} — awaiting ER readiness confirmation (auto-timeout 180 s → regional protocol fallback)`],
    CONFIRMED: ["ok", `Handshake CONFIRMED by ${handshake.hospital_id} — destination locked. Anticipated ESI-${handshake.anticipated_esi ?? "?"}`],
    CONSTRAINED_REROUTE_REQUESTED: ["bad", `CONSTRAINED — ${handshake.hospital_id} requests reroute: ${handshake.constraint_detail || "operational constraint"}. Re-rank destinations.`],
    TIMED_OUT: ["bad", `Handshake TIMED OUT (180 s). Deterministic fallback: regional protocol routing.`],
  }[handshake.status] || ["pending", ""];
  return `<div class="hs-banner"><span class="dot ${map[0]}"></span>${map[1]}</div>`;
}

function resultsHTML() {
  const a = assessment;
  let html = `<h2>Ranked Destinations — TTDC Optimizer</h2>
  <div class="news2-banner"><span class="score band-${a.news2_risk_band}">${a.news2}</span>
    <span>NEWS2 · <b class="band-${a.news2_risk_band}">${a.news2_risk_band}</b> risk band · tag <b>#${a.care_tag}</b></span></div>`;
  for (const r of a.rankings) {
    const h = r.hospital;
    html += `<div class="card ${r.rank === 1 ? "top" : ""} ${r.eligible ? "" : "ineligible"}">
      <div class="row1"><span class="rank-badge">${r.eligible ? "#" + r.rank : "–"}</span><h3>${h.name}</h3>${fmtFresh(h)}</div>
      ${r.eligible ? `
      <div class="metrics">
        <div class="metric"><b>${r.t_drive_min}′</b><span>Drive</span></div>
        <div class="metric"><b>${r.t_offload_min}′</b><span>Offload</span></div>
        <div class="metric"><b>${r.t_readiness_min < 0 ? "n/a" : r.t_readiness_min + "′"}</b><span>Spec. prep</span></div>
      </div>
      <div class="ttdc">TTDC <b>${r.ttdc_min} min</b> · beds ${h.beds_available} (conf-adj ${h.confidence_adjusted_beds}) · ICU ${h.icu_beds_available} · P(Cap≥1) ${Math.round((h.capacity_probability || 0.8) * 100)}%</div>
      ${h.stale ? `<div class="stale-flag">⚠️ UNVERIFIED / STALE — Model forecast (~${Math.round((h.capacity_probability || 0.8) * 100)}% prob) — handshake required before destination lock</div>` : ""}
      <div style="margin-top:8px"><button class="btn secondary" data-hs="${h.id}">Request readiness handshake</button></div>`
      : `<div class="ineligible-reason">INELIGIBLE: ${r.ineligibility_reason}</div>`}
    </div>`;
  }
  html += `<h2>Why? — Explainable Routing</h2><ul class="rationale">` +
    a.rationale.map(x => `<li class="${x.startsWith("WARNING") ? "warn" : ""}">${x}</li>`).join("") + `</ul>`;
  return html;
}

function readVitals() {
  return {
    respiration_rate: +$("#rr").value, spo2: +$("#spo2").value,
    systolic_bp: +$("#sbp").value, heart_rate: +$("#hr").value,
    consciousness: $("#avpu").value, temperature: +$("#temp").value,
  };
}

async function runAssessment() {
  lastVitals = readVitals();
  const body = { ambulance_id: AMB_ID, latitude: pos.lat, longitude: pos.lon, vitals: lastVitals, care_tag: lastTag };
  try {
    assessment = await api("/api/assessments", { method: "POST", body });
    handshake = null;
  } catch (e) { alert("Assessment failed: " + e.message); }
  renderPanel();
}

async function requestHandshake(hid) {
  if (!lastVitals) lastVitals = readVitals();
  const body = { ambulance_id: AMB_ID, latitude: pos.lat, longitude: pos.lon, vitals: lastVitals, care_tag: lastTag };
  try { handshake = await api(`/api/handshake?hospital_id=${hid}`, { method: "POST", body }); chime("request"); reconnectWS(); }
  catch (e) { alert("Handshake failed: " + e.message); }
  renderPanel();
}

/* =====================================================================
   VIEW: Hospital ER HUD
===================================================================== */
let pendingRequest = null;
function hospitalView() {
  const selOpts = hospitals.map(h => `<option value="${h.id}" ${h.id === hospitalSelection ? "selected" : ""}>${h.name}</option>`).join("");
  let html = `<div class="mute-row"><button id="muteBtn">${muted ? "Alerts muted — unmute" : "Mute alerts"}</button></div>
  <div class="field"><label>Station (this ER triage terminal)</label><select id="hospSel">${selOpts}</select></div>
  <h2>Inbound Pre-Arrival Queue</h2>`;
  if (pendingRequest) {
    const v = pendingRequest.handshake.patient.vitals;
    const p = pendingRequest.handshake.patient;
    html += `<div class="card alert-card"><div class="row1"><h3>PRE-ARRIVAL HANDSHAKE REQUEST — #${p.care_tag}</h3>
      <span class="fresh warn">ETA ${pendingRequest.handshake.eta_min}′</span></div>
      <table class="vitals-table">
        <tr><td>Incident</td><td>${p.incident_id} (pseudo-anonymous)</td></tr>
        <tr><td>NEWS2</td><td class="band-${p.news2_risk_band}">${p.news2} · ${p.news2_risk_band}</td></tr>
        <tr><td>Suggested ESI (chief review)</td><td>${pendingRequest.suggested_esi}</td></tr>
        <tr><td>RR / SpO₂ / SBP</td><td>${v.respiration_rate} / ${v.spo2}% / ${v.systolic_bp}</td></tr>
        <tr><td>HR / Temp / AVPU</td><td>${v.heart_rate} / ${v.temperature}°C / ${v.consciousness}</td></tr>
      </table>
      <div class="field"><label>Anticipated ESI level (triage nurse assigns)</label>
        <select id="esiSel">${[1, 2, 3, 4, 5].map(i => `<option ${i === pendingRequest.suggested_esi ? "selected" : ""} value="${i}">ESI-${i}</option>`).join("")}</select></div>
      <div class="hs-actions">
        <button class="btn" id="hsConfirm">Acknowledge Readiness</button>
        <button class="btn danger" id="hsConstrain">Report Constraint</button>
      </div></div>`;
  } else {
    html += `<p class="rationale">No pending pre-arrival requests for this station. Awaiting WebSocket push…</p>`;
  }
  const me = hospitals.find(h => h.id === hospitalSelection);
  if (me) {
    html += `<h2>My Facility State</h2><div class="card">
      <div class="row1"><h3>${me.name}</h3>${fmtFresh(me)}</div>
      <div class="metrics">
        <div class="metric"><b>${me.beds_available}</b><span>ED beds</span></div>
        <div class="metric"><b>${me.icu_beds_available}</b><span>ICU</span></div>
        <div class="metric"><b>${me.active_boarders}</b><span>Boarders</span></div>
      </div>
      <div class="ttdc">Specialist: <b>${me.specialist_status}</b> · CT: <b>${me.ct_operational ? "operational" : "OFFLINE"}</b></div>
      <h2>Pre-Arrival Checklist</h2>
      <ul class="rationale">
        <li>☐ Stage trauma bay / mobilize Cath Lab per care tag</li>
        <li>☐ Prep blood units if #TRAUMA</li>
        <li>☐ Notify on-call interventionalist if ESI-1 anticipated</li>
      </ul></div>`;
  }
  return html;
}

async function ackHandshake(confirm) {
  if (!pendingRequest) return;
  const constraint = confirm ? "" : (prompt("Constraint detail (sent to ambulance):", "Cath Lab occupied — ETA 25 min") || "operational constraint");
  const esi = +($("#esiSel")?.value || pendingRequest.suggested_esi);
  await api(`/api/handshake/${pendingRequest.handshake.id}/ack?confirm=${confirm}&constraint=${encodeURIComponent(constraint)}&anticipated_esi=${esi}`, { method: "POST" });
  pendingRequest = null;
  renderPanel();
}

/* =====================================================================
   VIEW: Surge Simulator + Counterfactual Sandbox
===================================================================== */
function simView() {
  let html = `<h2>Multi-Hospital Network — Live Synthetic State</h2>`;
  for (const h of hospitals) {
    html += `<div class="card"><div class="row1"><h3>${h.name}</h3>${fmtFresh(h)}</div>
      <div class="metrics">
        <div class="metric"><b>${h.beds_available}</b><span>Beds</span></div>
        <div class="metric"><b>${h.active_boarders}</b><span>Boarders</span></div>
        <div class="metric"><b>${h.inbound_ambulances}</b><span>Inbound</span></div>
      </div>
      <div class="ttdc">ICU ${h.icu_beds_available} · ${h.specialist_status} · CT ${h.ct_operational ? "OK" : "OFFLINE"} · conf-adj beds ${h.confidence_adjusted_beds}</div>
      <div class="hs-actions" style="margin-top:8px">
        <button class="btn secondary" data-ev="${h.id}:refresh">Publish bed update</button>
        <button class="btn secondary" data-ev="${h.id}:boarder">+1 boarder</button>
        <button class="btn secondary" data-ev="${h.id}:ct">Toggle CT</button>
        <button class="btn secondary" data-ev="${h.id}:spec">Cycle specialist</button>
      </div></div>`;
  }
  html += `<h2>Counterfactual Sandbox — “What If?”</h2>
    <div class="card"><p class="rationale">Re-run the last ranking under a modified single-hospital state, without touching the live network.</p>
    <div class="field"><label>Hospital to modify</label><select id="wiHosp">${hospitals.map(h => `<option>${h.id} — ${h.name}</option>`).join("")}</select></div>
    <div class="grid2">
      <div class="field"><label>Beds available</label><input id="wiBeds" type="number" placeholder="leave blank to keep"></div>
      <div class="field"><label>Boarders</label><input id="wiBoard" type="number" placeholder="keep"></div>
    </div>
    <div class="field"><label>CT operational</label><select id="wiCT"><option value="">keep</option><option value="true">online</option><option value="false">offline</option></select></div>
    <button class="btn" id="btnWhatIf" ${assessment ? "" : "disabled"}>Run What-If (uses last field assessment)</button>
    ${assessment ? "" : `<p class="rationale" style="margin-top:8px">Run an assessment in the Cockpit first.</p>`}
    <div id="wiResult" style="margin-top:12px"></div></div>`;
  return html;
}

async function injectEvent(spec) {
  const [hid, kind] = spec.split(":");
  const me = hospitals.find(h => h.id === hid);
  let body = { hospital_id: hid };
  if (kind === "refresh") body.beds_available = Math.max(0, me.beds_available + (Math.random() < 0.5 ? -1 : 1));
  if (kind === "boarder") { body.active_boarders = me.active_boarders + 1; body.refresh_timestamp = false; }
  if (kind === "ct") { body.ct_operational = !me.ct_operational; }
  if (kind === "spec") {
    const order = ["ACTIVE", "ON_CALL", "UNAVAILABLE"];
    body.specialist_status = order[(order.indexOf(me.specialist_status) + 1) % 3];
  }
  await api("/api/hospitals/event", { method: "POST", body });
}

async function runWhatIf() {
  if (!assessment) return;
  const hid = $("#wiHosp").value.split(" — ")[0];
  const overrides = { hospital_id: hid };
  if ($("#wiBeds").value !== "") overrides.beds_available = +$("#wiBeds").value;
  if ($("#wiBoard").value !== "") { overrides.active_boarders = +$("#wiBoard").value; overrides.refresh_timestamp = false; }
  if ($("#wiCT").value !== "") overrides.ct_operational = $("#wiCT").value === "true";
  const body = { assessment: { ambulance_id: AMB_ID, latitude: pos.lat, longitude: pos.lon, vitals: lastVitals || { respiration_rate: 18, spo2: 97, systolic_bp: 124, heart_rate: 88, consciousness: "A", temperature: 37 }, care_tag: lastTag }, overrides };
  const res = await api("/api/whatif", { method: "POST", body });
  $("#wiResult").innerHTML = `<h2>Counterfactual Ranking</h2>` + res.rankings.map(r =>
    `<div class="card ${r.rank === 1 ? "top" : ""} ${r.eligible ? "" : "ineligible"}">
      <div class="row1"><span class="rank-badge">${r.eligible ? "#" + r.rank : "–"}</span><h3>${r.hospital.name}</h3></div>
      ${r.eligible ? `<div class="ttdc">TTDC <b>${r.ttdc_min} min</b> (drive ${r.t_drive_min}′ + offload ${r.t_offload_min}′ + prep ${r.t_readiness_min < 0 ? "n/a" : r.t_readiness_min + "′"})</div>`
        : `<div class="ineligible-reason">${r.ineligibility_reason}</div>`}
    </div>`).join("") +
    `<ul class="rationale">${res.rationale.map(x => `<li>${x}</li>`).join("")}</ul>`;
}

/* ================================================================= boot */
function renderPanel() {
  const panel = document.getElementById("panel");
  panel.innerHTML = role === "cockpit" ? cockpitView() : role === "hospital" ? hospitalView() : simView();
  bindPanel();
}
function bindPanel() {
  document.querySelectorAll(".tags button").forEach(b => b.onclick = () => {
    document.querySelectorAll(".tags button").forEach(x => x.classList.remove("active"));
    b.classList.add("active"); lastTag = b.dataset.tag;
  });
  const br = $("#btnRank"); if (br) br.onclick = runAssessment;
  document.querySelectorAll("[data-hs]").forEach(b => b.onclick = () => requestHandshake(b.dataset.hs));
  const hsC = $("#hsConfirm"); if (hsC) hsC.onclick = () => ackHandshake(true);
  const hsX = $("#hsConstrain"); if (hsX) hsX.onclick = () => ackHandshake(false);
  const mute = $("#muteBtn"); if (mute) mute.onclick = () => { muted = !muted; renderPanel(); };
  const selH = $("#hospSel"); if (selH) selH.onchange = () => { hospitalSelection = selH.value; pendingRequest = null; reconnectWS(); renderPanel(); };
  document.querySelectorAll("[data-ev]").forEach(b => b.onclick = () => injectEvent(b.dataset.ev));
  const wi = $("#btnWhatIf"); if (wi) wi.onclick = runWhatIf;
}
function reconnectWS() { try { ws.close(); } catch {} connectWS(); }

document.querySelectorAll("nav.roles button").forEach(b => b.onclick = () => {
  document.querySelectorAll("nav.roles button").forEach(x => x.classList.remove("active"));
  b.classList.add("active"); role = b.dataset.role; reconnectWS(); renderPanel();
});

setInterval(() => { document.getElementById("clock").textContent = new Date().toLocaleTimeString(); }, 1000);

(async () => {
  hospitals = await api("/api/hospitals");
  initMap();
  renderMapMarkers();
  renderPanel();
  connectWS();
  setInterval(async () => { try { hospitals = await api("/api/hospitals"); renderMapMarkers(); if (role === "sim") renderPanel(); } catch {} }, 15000);
})();
