import { getJSON } from "../api.js";
import { set, state } from "../state.js";
import { $, esc } from "../ui/dom.js";
import { accessChip, coord, km } from "../ui/format.js";

const DISCLAIMER =
  "No public AIS is not evidence of wrongdoing. Small boats are not required to carry AIS, state vessels often do not broadcast, and reception can fail.";

export function setTitle(text) {
  $("card-title").textContent = text;
}

export function setBody(html) {
  $("card-body").innerHTML = html;
}

export function hideCard() {
  $("card").hidden = true;
  set({ selectedDetection: null });
}

function showCard() {
  $("card").hidden = false;
}

function pct(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function scoreBar(score, threshold, vesselLike) {
  const s = Math.max(0, Math.min(1, Number(score) || 0));
  const t = Math.max(0, Math.min(1, Number(threshold) || 0));
  const fill = vesselLike ? "" : " low";
  return (
    `<div class="score-bar" title="score ${s.toFixed(2)}, threshold ${t.toFixed(3)}">` +
    `<div class="score-fill${fill}" style="width:${(s * 100).toFixed(1)}%"></div>` +
    `<span class="score-tick" style="left:${(t * 100).toFixed(1)}%"></span>` +
    `</div>` +
    `<p class="hint">${s.toFixed(2)} · ${vesselLike ? "vessel-like" : "not vessel-like"}</p>`
  );
}

function classifierCaption() {
  const model = state.model;
  if (model && model.available === false) {
    return `<p class="micro">precomputed; live classifier unavailable</p>`;
  }
  return "";
}

function persistenceCopy(verdict) {
  if (verdict === "persistent") {
    return "Persistent: present on every covered pass, likely land or a fixed structure";
  }
  if (verdict === "transient") {
    return "Transient: absent on other passes";
  }
  return verdict || "—";
}

function statusLine(ev) {
  const status = ev.candidate_status;
  if (status === "dark_candidate") {
    return "Dark candidate: vessel-like, transient, no public AIS at the time of the pass.";
  }
  if (status === "deprioritized") {
    const verdict = ev.persistence && ev.persistence.verdict;
    if (verdict === "persistent") {
      return "Deprioritized: persistent on every covered pass, likely land or a fixed structure.";
    }
    return "Deprioritized: not vessel-like.";
  }
  if (status === "unreviewed") {
    return "Unreviewed: unmatched, no evidence entry.";
  }
  return "Matched to public AIS.";
}

function vesselList(ctx) {
  const vessels = (ctx && ctx.vessels) || [];
  if (!vessels.length) return "";
  const rows = vessels.map((v) => {
    const id = v.matched_detection ? ` → ${esc(v.matched_detection)}` : "";
    const dist = v.matched_detection_km != null ? ` (${esc(v.matched_detection_km)} km)` : "";
    return `<li>${esc(v.name || v.mmsi)}${id}${dist}</li>`;
  }).join("");
  return `<details class="vessel-list"><summary>Vessels</summary><ul>${rows}</ul></details>`;
}

function compactClassifier(ev) {
  const c = ev.classifier || {};
  if (c.score == null) return "";
  return (
    `<div class="evidence-row">` +
    `<div class="evidence-head"><h2>Classifier</h2><span class="chip">MODELED</span></div>` +
    classifierCaption() +
    (c.chip_url ? `<img class="chip-img" src="${esc(c.chip_url)}" alt="${esc(ev.id)} chip" />` : "") +
    scoreBar(c.score, c.threshold, c.vessel_like) +
    `</div>`
  );
}

function unmatchedPanel(ev) {
  const p = ev.detection || {};
  const ctx = ev.ais_context || {};
  const c = ev.classifier || {};
  const pers = ev.persistence;
  const nearest = p.nearest_ais_km != null ? km(p.nearest_ais_km) : "—";
  return (
    `<div class="evidence-row">` +
    `<div class="evidence-head"><h2>AIS</h2><span class="chip">SNAPSHOT 02 NOV</span></div>` +
    `<div class="kv"><span>Nearest AIS</span><b>${esc(nearest)}</b></div>` +
    `<p class="hint">${esc(ctx.summary || "")}</p>` +
    vesselList(ctx) +
    `</div>` +
    `<div class="evidence-row">` +
    `<div class="evidence-head"><h2>Classifier</h2><span class="chip">MODELED</span></div>` +
    classifierCaption() +
    (c.chip_url ? `<img class="chip-img" src="${esc(c.chip_url)}" alt="${esc(ev.id)} chip" />` : "") +
    scoreBar(c.score, c.threshold, c.vessel_like) +
    `</div>` +
    `<div class="evidence-row">` +
    `<div class="evidence-head"><h2>Persistence</h2><span class="chip">REVIEWED</span></div>` +
    (pers && pers.strip_url ? `<img class="chip-img" src="${esc(pers.strip_url)}" alt="${esc(ev.id)} persistence" />` : "") +
    `<p class="hint">${esc(persistenceCopy(pers && pers.verdict))}</p>` +
    `<p class="micro">analyst-reviewed</p>` +
    `</div>` +
    `<div class="evidence-row">` +
    `<div class="evidence-head"><h2>Status</h2></div>` +
    `<p>${esc(statusLine(ev))}</p>` +
    `</div>` +
    `<p class="disclaimer">${esc(DISCLAIMER)}</p>` +
    (ev.candidate_status === "dark_candidate" ? darkActions(ev.id) : "")
  );
}

function darkActions(detId) {
  return (
    `<div class="case-actions">` +
    `<button type="button" data-reacquire="${esc(detId)}">Reacquire</button>` +
    `<a href="/case.html?id=${esc(detId)}" target="_blank" rel="noopener">Open case file</a>` +
    `</div>`
  );
}

function fracPct(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${Math.round(n * 100)}%`;
}

export function showPlan(plan) {
  const det = (plan && plan.detection) || {};
  const best = plan && plan.best_next;
  const clipped = plan && plan.clipped_to_coastline
    ? "Reach clipped to sea."
    : "Reach not clipped to coastline.";
  const visible = [...(plan.passes || [])]
    .sort((a, b) => Number(a.hours_after) - Number(b.hours_after))
    .slice(0, 5);
  const rows = visible.map((p) => {
    const on = p.best ? " on" : "";
    const tasked = p.coverage === "tasked"
      ? `<span class="chip commercial">possible, requires tasking</span>`
      : `<span class="chip">systematic</span>`;
    return (
      `<button type="button" class="plan-pass${on}" data-pass-norad="${p.norad}" data-pass-center="${esc(p.center)}" aria-pressed="${p.best ? "true" : "false"}">` +
      `<span>${esc(p.name)}</span>` +
      `<span class="micro">${esc(String(p.hours_after))} h · typical ${esc(fracPct(p.coverage_frac && p.coverage_frac.typical))}</span>` +
      tasked +
      `</button>`
    );
  }).join("");
  setTitle(`REACQUIRE · ${det.id || ""}`);
  setBody(
    `<p class="hint">${esc(clipped)} Slow 6 kn / typical 12 kn / fast 20 kn.</p>` +
    (best
      ? `<p class="hint">Best next chance: ${esc(best.name)} at ${esc(best.center)} (${esc(String(best.hours_after))} h).</p>`
      : `<p class="hint">No covering pass in the next 48 hours.</p>`) +
    `<div class="plan-list">${rows}</div>` +
    `<div class="case-actions">` +
    `<button type="button" data-clear-plan>Clear plan</button>` +
    `<a href="/case.html?id=${esc(det.id || "")}" target="_blank" rel="noopener">Open case file</a>` +
    `</div>`,
  );
  showCard();
}

export function markPlanPass(norad, center) {
  const wantNorad = String(norad ?? "");
  const wantCenter = String(center ?? "");
  document.querySelectorAll(".plan-pass").forEach((btn) => {
    const on = btn.getAttribute("data-pass-norad") === wantNorad
      && btn.getAttribute("data-pass-center") === wantCenter;
    btn.classList.toggle("on", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  });
}

function matchedPanel(ev) {
  const p = ev.detection || {};
  return (
    `<p><span class="chip open">AIS ${esc(p.name || p.mmsi)}</span></p>` +
    `<p class="hint">${km(p.match_km)} from public AIS.</p>` +
    compactClassifier(ev)
  );
}

function satellitePose(rec) {
  return (rec && state.sats.find((item) => item.rec.norad === rec.norad)) || null;
}

function formatLat(lat) {
  if (lat == null || Number.isNaN(Number(lat))) return "—";
  const value = Number(lat);
  return `${Math.abs(value).toFixed(3)}°${value >= 0 ? "N" : "S"}`;
}

function formatLon(lon) {
  if (lon == null || Number.isNaN(Number(lon))) return "—";
  const value = Number(lon);
  return `${Math.abs(value).toFixed(3)}°${value >= 0 ? "E" : "W"}`;
}

function formatAlt(altKm) {
  if (altKm == null || Number.isNaN(Number(altKm))) return "—";
  return `${Number(altKm).toFixed(0)} km`;
}

function writeHudCursor(sat) {
  const el = $("hud-cursor");
  if (!el) return;
  if (sat && sat.lat != null && sat.lon != null) {
    el.textContent = coord(sat.lat, sat.lon);
    return;
  }
  el.textContent = "—";
}

export function paintSelectedSatellite() {
  const rec = state.selectedSatellite;
  if (!rec) return;
  const sat = satellitePose(rec);
  const latEl = $("sat-lat");
  const lonEl = $("sat-lon");
  const altEl = $("sat-alt");
  if (latEl) latEl.textContent = formatLat(sat && sat.lat);
  if (lonEl) lonEl.textContent = formatLon(sat && sat.lon);
  if (altEl) altEl.textContent = formatAlt(sat && sat.altKm);
  writeHudCursor(sat);
}

export function showSatellite(rec) {
  const spec = state.missions[rec.family];
  const access = spec ? `<span class="chip ${esc(spec.access)}">${esc(accessChip(spec.access))}</span>` : "";
  const sat = satellitePose(rec);
  setTitle(rec.name);
  setBody(
    `<div class="kv"><span>Family</span><b>${esc(rec.family)}</b></div>` +
    `<div class="kv"><span>NORAD</span><b>${rec.norad}</b></div>` +
    `<div class="kv"><span>Latitude</span><b id="sat-lat">${esc(formatLat(sat && sat.lat))}</b></div>` +
    `<div class="kv"><span>Longitude</span><b id="sat-lon">${esc(formatLon(sat && sat.lon))}</b></div>` +
    `<div class="kv"><span>Altitude</span><b id="sat-alt">${esc(formatAlt(sat && sat.altKm))}</b></div>` +
    (spec ? `<p>${access} <span class="micro">${esc(spec.band)}-BAND</span></p>` : "") +
    `<p class="hint">${esc(rec.note || rec.label || "")}</p>`,
  );
  showCard();
  writeHudCursor(sat);
}

function fallbackBody(p) {
  if (p.matched) {
    return (
      `<p><span class="chip open">AIS ${esc(p.name || p.mmsi)}</span></p>` +
      `<p class="hint">${km(p.match_km)} from public AIS.</p>`
    );
  }
  return (
    `<p><span class="chip commercial">not on public AIS</span></p>` +
    `<p class="disclaimer">${esc(DISCLAIMER)}</p>`
  );
}

export async function showDetection(feature) {
  const p = feature.properties;
  set({ selectedDetection: feature });
  setTitle(p.id);
  setBody(`<p class="hint">Loading evidence…</p>`);
  showCard();
  try {
    const ev = await getJSON(`/api/evidence/${encodeURIComponent(p.id)}`);
    setBody(p.matched ? matchedPanel(ev) : unmatchedPanel(ev));
  } catch {
    setBody(fallbackBody(p));
  }
}

export function focusDetection(feature) {
  const [lon, lat] = feature.geometry.coordinates;
  state.viewer.trackedEntity = undefined;
  state.viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(lon, lat, 25000),
    duration: 2.5,
    easingFunction: Cesium.EasingFunction.CUBIC_IN_OUT,
  });
  return showDetection(feature);
}

export async function showModelCard() {
  let model = state.model;
  try {
    model = await getJSON("/api/model");
    set({ model });
  } catch {
    /* keep cached */
  }
  if (!model) {
    setTitle("SHIP CLASSIFIER");
    setBody(`<p class="hint">Model card unavailable.</p>`);
    showCard();
    return;
  }
  const test = model.test || {};
  const kat = model.kattegat || {};
  setTitle("SHIP CLASSIFIER");
  setBody(
    `<div class="hero-pair">` +
    `<div><span class="micro">Ships kept</span><p class="hero">${esc(pct(test.ships_kept))}</p></div>` +
    `<div><span class="micro">False alarms rejected</span><p class="hero">${esc(pct(test.cfar_false_alarms_rejected))}</p></div>` +
    `</div>` +
    `<p>${esc(kat.ais_confirmed_recognized)} of ${esc(kat.ais_confirmed_total)} AIS-confirmed ships recognized.</p>` +
    `<p class="hint">Miss: ${esc(kat.miss)}</p>` +
    `<div class="kv"><span>Threshold</span><b>${Number(model.threshold).toFixed(3)}</b></div>` +
    `<p class="hint">${esc(model.threshold_rule)}</p>` +
    `<p class="disclaimer">${esc(model.license)}</p>` +
    (model.available === false ? `<p class="micro">precomputed; live classifier unavailable</p>` : ""),
  );
  showCard();
}

function minutesAgo(iso) {
  if (!iso) return "—";
  const then = Date.parse(iso);
  if (!Number.isFinite(then)) return iso;
  const min = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (min < 1) return "just now";
  if (min === 1) return "1 min ago";
  if (min < 120) return `${min} min ago`;
  const hours = Math.round(min / 60);
  return `${hours} h ago`;
}

function shipFields(ship, extraNote) {
  return (
    `<div class="kv"><span>MMSI</span><b>${esc(ship.mmsi)}</b></div>` +
    `<div class="kv"><span>Category</span><b>${esc(ship.category || "other")}</b></div>` +
    `<div class="kv"><span>Speed</span><b>${ship.sog == null ? "—" : `${Number(ship.sog).toFixed(1)} kn`}</b></div>` +
    `<div class="kv"><span>Course</span><b>${ship.cog == null ? "—" : `${Number(ship.cog).toFixed(0)}°`}</b></div>` +
    `<div class="kv"><span>Last report</span><b>${esc(minutesAgo(ship.last_report))}</b></div>` +
    `<p class="hint">${esc(extraNote || "Self-reported AIS position. Not radar-verified.")}</p>`
  );
}

export function showGlobalShip(ship) {
  setTitle(ship.name || ship.mmsi);
  setBody(
    `<p><span class="chip">SELF-REPORTED AIS</span></p>` +
    shipFields(ship),
  );
  showCard();
}

export function showAisOnly(feature) {
  const p = feature.properties || {};
  setTitle(p.name || p.mmsi);
  setBody(
    `<p><span class="chip">AIS-ONLY IN SCENE</span></p>` +
    shipFields(
      {
        mmsi: p.mmsi,
        category: "other",
        sog: p.sog,
        cog: p.cog,
        last_report: (p.interpolated_from && p.interpolated_from[0]) || "",
      },
      p.note,
    ),
  );
  showCard();
}

export function idleInspector() {
  hideCard();
}
