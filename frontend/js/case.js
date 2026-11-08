import { getJSON } from "./api.js";
import { esc } from "./ui/dom.js";

const params = new URLSearchParams(location.search);
const detId = params.get("id") || "";
const root = document.getElementById("case");
let horizon = Number(params.get("horizon_h") || 3);
if (![1, 3, 6, 12].includes(horizon)) horizon = 3;

function num(value, digits = 2) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : "—";
}

function chipClass(access) {
  if (access === "open") return "chip open";
  if (access === "open-sample" || access === "sample") return "chip sample";
  if (access === "restricted") return "chip restricted";
  if (access === "commercial") return "chip commercial";
  return "chip";
}

function kv(label, value) {
  return `<div class="kv"><span>${esc(label)}</span><b>${value}</b></div>`;
}

function actionFacts(action) {
  const f = action.facts || {};
  if (action.id === "review_pass") {
    const links = (f.links || []).map((l) => `<a href="${esc(l.url)}">${esc(l.label)}</a>`).join(" · ");
    return `${esc(f.satellite)} at ${esc(f.time)} · ${esc(String(f.coverage_typical_pct))}% typical · ${esc(f.access_label || f.access)}${f.access_note ? ` · ${esc(f.access_note)}` : ""}${links ? ` · ${links}` : ""}`;
  }
  if (action.id === "patrol_search") {
    const c = f.corners || {};
    const port = f.nearest_port;
    const corners = ["sw", "se", "ne", "nw"].map((k) => c[k] && c[k].ddm).filter(Boolean).join(" · ");
    const p = port ? `${esc(port.name)} ${esc(String(port.distance_km))} km ${esc(port.bearing_compass)}${port.transit_h_20kn != null ? ` · ${esc(String(port.transit_h_20kn))} h at 20 kn` : ""}` : "";
    return `Horizon +${esc(String(f.horizon_h))} h. ${esc(corners)}. ${p}`;
  }
  if (action.id === "ais_history") {
    return `<a href="${esc(f.url)}">Global Fishing Watch</a> for the search box.`;
  }
  if (action.id === "mpa_rules") {
    return `${esc(f.name)} (${esc(f.designation || "protected area")})${f.in_mpa ? ", inside" : ""}.`;
  }
  if (action.id === "notify") {
    const auth = (f.authorities || []).map((a) => `<a href="${esc(a.url)}">${esc(a.label)}</a>`).join(" · ");
    return `${esc(f.method || "")} ${auth}`;
  }
  if (action.id === "task_commercial") {
    const links = (f.links || []).map((l) => `<a href="${esc(l.url)}">${esc(l.label)}</a>`).join(" · ");
    return `${esc(f.satellite)} at ${esc(f.time)}${links ? ` · ${links}` : ""}`;
  }
  return "";
}

function render(data) {
  const facts = data.facts || {};
  const case_ = facts.case || {};
  const tgt = facts.target || {};
  const jur = facts.jurisdiction || {};
  const mpa = jur.protected_area || {};
  const ais = facts.ais_context || {};
  const pers = facts.persistence || {};
  const pri = facts.priority || {};
  const nar = data.narrative || {};
  const prov = data.provenance || {};
  const review = data.review;
  const box = (facts.search_area || {}).search_box || {};
  const conf = tgt.confidence || {};
  const fp = tgt.footprint || {};
  const port = (facts.nearest_ports || [])[0];
  const signed = Boolean(review && review.decision);
  document.body.classList.toggle("signed", signed);
  document.title = `Nimbus case ${case_.id || detId}`;

  const readings = Object.fromEntries((nar.evidence_readings || []).map((r) => [r.item, r.reading]));
  const actionById = Object.fromEntries((facts.candidate_actions || []).map((a) => [a.id, a]));
  const mpaLine = mpa.in_mpa
    ? `Inside ${mpa.name}`
    : (mpa.near_mpa ? `${mpa.mpa_km} km from ${mpa.name}` : "No packaged protected area");
  const jurLine = jur.nearest_coast_country
    ? `${esc(jur.nearest_coast_country)} · 12 nm ${jur.likely_territorial_sea ? "yes" : "no"}`
    : "reference layer unavailable";
  const aisLine = `${ais.within_5km ? "yes" : "no"} · ${esc(String(ais.count || 0))} nearby, ${esc(String(ais.accounted_for || 0))} accounted for`;

  const growthRows = ((facts.search_area || {}).growth || []).map((row) => {
    const s = row.speeds || {};
    const cell = (key) => {
      const item = s[key] || {};
      return `${num(item.radius_km, 1)} km / ${num(item.area_km2, 0)} km²`;
    };
    return `<tr><td>+${esc(String(row.horizon_h))} h</td><td>${cell("slow")}</td><td>${cell("typical")}</td><td>${cell("fast")}</td></tr>`;
  }).join("");

  const cornerRows = ["sw", "se", "ne", "nw"].map((k) => {
    const pt = (box.corners || {})[k];
    if (!pt) return "";
    return `<tr><td>${esc(k.toUpperCase())}</td><td>${esc(pt.ddm)}</td><td>${esc(String(pt.lat))}, ${esc(String(pt.lon))}</td></tr>`;
  }).join("");

  const passRows = (facts.next_passes || []).map((p) => {
    const links = (p.links || []).map((l) => `<a href="${esc(l.url)}">${esc(l.label)}</a>`).join(" · ");
    return `<tr class="${p.best_next ? "best" : ""}">` +
      `<td>${esc(p.satellite)}</td><td>${esc(p.operator)}</td><td>${esc(p.band || "")}</td>` +
      `<td>${esc(p.coverage)}</td><td><span class="${chipClass(p.access)}">${esc(p.access_label || p.access)}</span></td>` +
      `<td>${esc(p.start)}</td><td>+${esc(String(p.hours_after))} h</td>` +
      `<td>${esc(String((p.coverage_pct || {}).typical))}%</td><td>${links}</td></tr>`;
  }).join("");

  const actions = (nar.recommended_actions || []).slice(0, 5).map((item, i) => {
    const src = actionById[item.action_id] || { id: item.action_id, facts: {} };
    return `<li><strong>${i + 1}. ${esc(src.title || item.action_id)}</strong> — ${esc(item.why)}<div class="hint">${actionFacts(src)}</div></li>`;
  }).join("");

  const alts = (nar.alternative_explanations || []).map((s) => `<li>${esc(s)}</li>`).join("");
  const vessels = (ais.vessels || []).map((v) => (
    `<tr><td>${esc(v.name)}</td><td>${esc(v.mmsi)}</td><td>${esc(v.start)}–${esc(v.end)}</td>` +
    `<td>${esc(v.matched_detection || "—")}</td><td>${v.matched_detection_km == null ? "—" : esc(String(v.matched_detection_km)) + " km"}</td></tr>`
  )).join("");

  const hz = [1, 3, 6, 12].map((h) => `<button type="button" data-horizon="${h}" class="${h === horizon ? "on" : ""}">+${h} h</button>`).join("");
  const q = `horizon_h=${horizon}`;
  const exports = ["gpx", "kml", "geojson", "json"].map((fmt) => (
    `<a href="/api/casefile/${encodeURIComponent(case_.id || detId)}/export.${fmt}?${q}">${fmt.toUpperCase()}</a>`
  )).join("");

  root.innerHTML =
    `<div class="watermark">DRAFT</div>` +
    `<div class="page-1">` +
    `<header class="band"><div>` +
    `<h1>Nimbus · Case ${esc(case_.id || detId)}</h1>` +
    `<p class="marking">${esc(case_.marking || "")}</p>` +
    `<p class="scene-id">${esc(case_.scene_id || "")}</p>` +
    `</div><div>` +
    `<span class="badge pri ${esc(pri.tier || "")}">${esc(pri.tier || "")}</span> ` +
    `<span class="badge">${esc(signed ? `${review.decision} · ${review.analyst}` : "DRAFT · NOT REVIEWED")}</span>` +
    `<p class="scene-id">${esc(case_.generated_at || "")}</p>` +
    `</div></header>` +
    `<p class="bluf">${esc(nar.bluf || "")}</p>` +
    `<p class="provenance">${esc(prov.line || "")}</p>` +
    `<div class="facts-grid">` +
    kv("Last known", `${esc(tgt.position_ddm)} · ${esc(String(tgt.lat))}, ${esc(String(tgt.lon))}`) +
    kv("Detected", esc(case_.acquisition_time_human || case_.acquisition_time)) +
    kv("Approx. length", esc((fp.length_m_range || "—") + (fp.note ? ` · ${fp.note}` : ""))) +
    kv("Detection confidence", `${conf.score == null ? "—" : num(conf.score, 2)} · threshold ${conf.threshold == null ? "—" : num(conf.threshold, 3)} · ${esc(conf.tier || "")}`) +
    kv("AIS within 5 km", esc(aisLine)) +
    kv("Persistence", esc((pers && pers.verdict) || "—")) +
    kv("Jurisdiction", `${jurLine}<div class="method-note">${esc(jur.method || "")}</div>`) +
    kv("Protected area", esc(mpaLine)) +
    kv("Nearest port", port ? `${esc(port.name)} ${esc(String(port.distance_km))} km ${esc(port.bearing_compass)}` : "reference layer unavailable") +
    kv("Peak / shore", `${tgt.peak_db == null ? "—" : esc(String(tgt.peak_db)) + " dB"} · ${tgt.shore_km == null ? "—" : num(tgt.shore_km, 1) + " km"}`) +
    `</div>` +
    `<section class="case-section"><h2>Map</h2>` +
    `<div class="horizons no-print">${hz}</div>` +
    `<div class="map-wrap"><img alt="Report map" src="/api/casefile/${encodeURIComponent(case_.id || detId)}/map.svg?${q}" /></div>` +
    `<table class="corners"><thead><tr><th>Corner</th><th>DDM</th><th>Decimal</th></tr></thead><tbody>${cornerRows}</tbody></table>` +
    `</section>` +
    `<section class="case-section"><h2>Search area growth</h2>` +
    `<table class="plan-table"><thead><tr><th>Horizon</th><th>6 kn</th><th>12 kn</th><th>20 kn</th></tr></thead>` +
    `<tbody>${growthRows}</tbody></table>` +
    `<p class="method-note">${(facts.search_area || {}).clipped_to_sea ? "Reach disks clipped to sea." : "Reach disks not clipped to coastline."} Constant speed, no routing.</p>` +
    `</section></div>` +
    `<section class="case-section"><h2>Evidence</h2>` +
    `<div class="evidence-row"><dt>AIS</dt><dd>${esc(readings.AIS || ais.summary || "—")}</dd><b>${esc(aisLine)}</b></div>` +
    `<div class="evidence-row"><dt>Classifier</dt><dd>${esc(readings.Classifier || "")}</dd><b>${conf.score == null ? "—" : num(conf.score, 2)}</b></div>` +
    `<div class="evidence-row"><dt>Persistence</dt><dd>${esc(readings.Persistence || "")}</dd><b>${esc((pers && pers.verdict) || "—")}</b></div>` +
    (tgt.chip_url ? `<img class="chip-img" src="${esc(tgt.chip_url)}" alt="${esc(case_.id || "")} chip" />` : "") +
    (pers && pers.strip_url ? `<img class="strip" src="${esc(pers.strip_url)}" alt="${esc(case_.id || "")} persistence" />` : "") +
    `<details><summary>AIS vessels nearby</summary>` +
    `<table class="ais-table"><thead><tr><th>Name</th><th>MMSI</th><th>Window</th><th>Matched</th><th>Distance</th></tr></thead>` +
    `<tbody>${vessels || `<tr><td colspan="5">None</td></tr>`}</tbody></table></details>` +
    `</section>` +
    `<section class="case-section"><h2>Assessment</h2>` +
    `<p>${esc(nar.assessment || "")}</p>` +
    `<p>${esc(nar.priority_rationale || "")}</p>` +
    `<ul class="alts">${alts}</ul>` +
    `<p class="hint">${esc(nar.confidence_statement || "")}</p>` +
    `</section>` +
    `<section class="case-section"><h2>Next 5 satellite passes</h2>` +
    `<table class="plan-table"><thead><tr><th>Satellite</th><th>Operator</th><th>Band</th><th>Type</th><th>Access</th><th>UTC</th><th>+h</th><th>12 kn</th><th>Links</th></tr></thead>` +
    `<tbody>${passRows || `<tr><td colspan="9">No covering pass in 48 h.</td></tr>`}</tbody></table>` +
    `</section>` +
    `<section class="case-section"><h2>Recommended actions</h2><ol class="actions">${actions}</ol></section>` +
    `<section class="case-section no-print"><h2>Exports</h2><div class="exports">` +
    `<button type="button" id="case-print-2">PDF</button>${exports}` +
    `<button type="button" id="case-regen">Regenerate narrative</button>` +
    `</div></section>` +
    `<section class="case-section"><h2>Method and limits</h2>` +
    `<p class="hint">${esc(((facts.method || {}).model || {}).arch || "")} · test AP ${esc(String((((facts.method || {}).model || {}).test || {}).ap || ""))}</p>` +
    `<p class="disclaimer">${esc(facts.limits || data.limits || "")}</p>` +
    `<p class="method-note">${esc((facts.priority || {}).rule || "")}</p>` +
    `<p class="method-note">${esc(jur.method || "")}</p>` +
    `</section>` +
    `<section class="case-section"><h2>Analyst review</h2>` +
    (signed ? `<p>${esc(review.analyst)} · ${esc(review.decision)} · ${esc(review.signed_at || "")}<br>${esc(review.notes || "")}</p>` : `<p class="hint">Not reviewed.</p>`) +
    `<form class="review-form no-print" id="review-form">` +
    `<label>Name <input name="analyst" required /></label>` +
    `<label>Decision <select name="decision"><option>Verify further</option><option>Refer</option><option>Dismiss</option></select></label>` +
    `<label>Notes <textarea name="notes" rows="3"></textarea></label>` +
    `<button type="submit">Sign</button></form></section>` +
    `<p class="no-print hint"><a href="/brief.html">Incident brief</a></p>`;
}

async function load() {
  return getJSON(`/api/casefile/${encodeURIComponent(detId)}?horizon_h=${horizon}`);
}

async function main() {
  document.getElementById("case-print").addEventListener("click", () => window.print());
  if (!detId) {
    root.innerHTML = `<p>Missing detection id. Open this page as <code>case.html?id=D002</code>.</p>`;
    return;
  }
  try {
    render(await load());
  } catch (err) {
    root.innerHTML = `<p>${esc(err.message || "Case file unavailable.")}</p>`;
    return;
  }
  root.addEventListener("click", async (ev) => {
    const hz = ev.target.closest("[data-horizon]");
    if (hz) {
      horizon = Number(hz.dataset.horizon);
      const url = new URL(location.href);
      url.searchParams.set("horizon_h", String(horizon));
      history.replaceState(null, "", url);
      render(await load());
      return;
    }
    if (ev.target.id === "case-print-2") window.print();
    if (ev.target.id === "case-regen") {
      ev.target.disabled = true;
      try {
        const data = await fetch(`/api/casefile/${encodeURIComponent(detId)}/narrative/regenerate?horizon_h=${horizon}`, { method: "POST" }).then((r) => r.json());
        render(data);
      } finally {
        /* button is rebuilt */
      }
    }
  });
  root.addEventListener("submit", async (ev) => {
    if (ev.target.id !== "review-form") return;
    ev.preventDefault();
    const form = new FormData(ev.target);
    const res = await fetch(`/api/casefile/${encodeURIComponent(detId)}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        analyst: form.get("analyst"),
        decision: form.get("decision"),
        notes: form.get("notes"),
      }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      root.querySelector(".review-form").insertAdjacentHTML("beforeend", `<p class="hint">${esc(body.error || "Review failed")}</p>`);
      return;
    }
    render(await load());
  });
}

main();
