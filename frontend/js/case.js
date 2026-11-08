import { getJSON } from "./api.js";
import { esc } from "./ui/dom.js";

const params = new URLSearchParams(location.search);
const detId = params.get("id") || "";
const root = document.getElementById("case");

function pct(value) {
  const n = Number(value);
  return Number.isFinite(n) ? `${Math.round(n * 100)}%` : "—";
}

function nearestPasses(plan, n = 5) {
  return [...(plan.passes || [])]
    .sort((a, b) => Number(a.hours_after) - Number(b.hours_after))
    .slice(0, n);
}

function ringSvg(plan) {
  const hours = (plan.best_next && plan.best_next.hours_after) || 12;
  const speeds = plan.speeds_kn || { slow: 6, typical: 12, fast: 20 };
  const maxKm = hours * speeds.fast * 1.852;
  const cx = 140;
  const cy = 140;
  const scale = 110 / Math.max(maxKm, 1);
  const rings = [
    { kn: speeds.fast, label: "20 kn" },
    { kn: speeds.typical, label: "12 kn" },
    { kn: speeds.slow, label: "6 kn" },
  ];
  const circles = rings.map((ring) => {
    const r = hours * ring.kn * 1.852 * scale;
    return `<circle cx="${cx}" cy="${cy}" r="${r.toFixed(1)}" fill="none" stroke="#f5a524" stroke-opacity="0.85"/>` +
      `<text x="${cx + 4}" y="${(cy - r + 10).toFixed(1)}" fill="#f5a524" font-size="9">${esc(ring.label)}</text>`;
  }).join("");
  return (
    `<svg class="case-map" viewBox="0 0 280 280" role="img" aria-label="Reach rings">` +
    `<rect width="280" height="280" fill="#071018"/>` +
    circles +
    `<circle cx="${cx}" cy="${cy}" r="3.5" fill="#ff4d4f"/>` +
    `</svg>`
  );
}

function evidenceBlock(data) {
  const ev = data.evidence || {};
  const ctx = ev.ais_context || {};
  const c = ev.classifier || {};
  const pers = ev.persistence || {};
  const det = ev.detection || data.detection || {};
  return (
    `<section class="case-section"><h2>Evidence</h2>` +
    `<div class="kv"><span>AIS</span><b>${esc(ctx.summary || "—")}</b></div>` +
    `<div class="kv"><span>Classifier</span><b>${c.score == null ? "—" : Number(c.score).toFixed(2)} · threshold ${c.threshold == null ? "—" : Number(c.threshold).toFixed(3)}</b></div>` +
    `<div class="kv"><span>Persistence</span><b>${esc((pers && pers.verdict) || "—")}</b></div>` +
    `<div class="kv"><span>Status</span><b>${esc(ev.candidate_status || det.candidate_status || "—")}</b></div>` +
    `<div class="evidence-grid">` +
    (c.chip_url ? `<img src="${esc(c.chip_url)}" alt="${esc(det.id || "")} chip" />` : "") +
    (pers.strip_url ? `<img src="${esc(pers.strip_url)}" alt="${esc(det.id || "")} persistence" />` : "") +
    `</div></section>`
  );
}

function locationBlock(data) {
  const det = data.detection || {};
  const mpa = det.in_mpa
    ? `Inside ${det.mpa_name}`
    : (det.near_mpa ? `${det.mpa_km} km from ${det.mpa_name}` : "No packaged protected area");
  return (
    `<section class="case-section"><h2>Location</h2>` +
    `<div class="kv"><span>Latitude</span><b>${Number(det.lat).toFixed(5)}</b></div>` +
    `<div class="kv"><span>Longitude</span><b>${Number(det.lon).toFixed(5)}</b></div>` +
    `<div class="kv"><span>Distance to shore</span><b>${det.shore_km == null ? "—" : `${Number(det.shore_km).toFixed(1)} km`}</b></div>` +
    `<div class="kv"><span>Protected area</span><b>${esc(mpa)}</b></div>` +
    ringSvg(data.plan || {}) +
    `</section>`
  );
}

function planBlock(plan) {
  const rows = nearestPasses(plan, 5).map((p) => {
    const cls = p.best ? "best" : "";
    const fr = p.coverage_frac || {};
    const kind = p.coverage === "tasked" ? "tasked" : "systematic";
    return (
      `<tr class="${cls}">` +
      `<td>${esc(p.name)}</td>` +
      `<td>${esc(p.center)}</td>` +
      `<td>${esc(String(p.hours_after))} h</td>` +
      `<td>${esc(kind)} · ${pct(fr.typical)}</td>` +
      `</tr>`
    );
  }).join("");
  const clip = plan.clipped_to_coastline ? "clipped to sea" : "not clipped to coastline";
  return (
    `<section class="case-section"><h2>Next five windows</h2>` +
    `<table class="plan-table"><thead><tr><th>Pass</th><th>UTC</th><th>After</th><th>Typical</th></tr></thead>` +
    `<tbody>${rows || `<tr><td colspan="4">No covering pass in 48 h.</td></tr>`}</tbody></table>` +
    `<p class="hint">6 / 12 / 20 kn constant-speed · ${esc(clip)}.</p>` +
    `</section>`
  );
}

function stepsBlock(steps) {
  const items = (steps || []).map((step) => {
    const links = (step.links || []).slice(0, 2).map((link) => `<a href="${esc(link.url)}">${esc(link.label)}</a>`).join(" · ");
    return `<li>${esc(step.text)}${links ? ` ${links}` : ""}</li>`;
  }).join("");
  return `<section class="case-section"><h2>Next steps</h2><ol class="steps">${items}</ol></section>`;
}

function render(data) {
  const det = data.detection || {};
  const scene = data.scene || {};
  document.title = `DarkWatch case file · ${det.id || detId}`;
  root.innerHTML =
    `<header class="case-head">` +
    `<div>` +
    `<h1>DarkWatch case file · ${esc(det.id || detId)}</h1>` +
    `<p class="hint">${esc(scene.scene_id || "")} · ${esc(scene.datetime || "")}</p>` +
    `</div></header>` +
    `<p>${esc(data.summary || "")}</p>` +
    evidenceBlock(data) +
    locationBlock(data) +
    planBlock(data.plan || {}) +
    stepsBlock(data.recommendations) +
    `<section class="case-section"><h2>Limits</h2><p class="disclaimer">${esc(data.limits || "")}</p></section>`;
}

async function main() {
  document.getElementById("case-print").addEventListener("click", () => window.print());
  if (!detId) {
    root.innerHTML = `<p>Missing detection id. Open this page as <code>case.html?id=D002</code>.</p>`;
    return;
  }
  try {
    render(await getJSON(`/api/casefile/${encodeURIComponent(detId)}`));
  } catch (err) {
    root.innerHTML = `<p>${esc(err.message || "Case file unavailable.")}</p>`;
  }
}

main();
