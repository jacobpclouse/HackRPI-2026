import { shipCounts } from "../globe/ships.js";
import { state } from "../state.js";
import { $ } from "../ui/dom.js";

export function renderLegend() {
  const box = $("legend");
  const families = {};
  for (const sat of state.sats) {
    const name = sat.rec.family;
    if (!families[name]) {
      const c = sat.color;
      const color = c && c.red != null
        ? `rgb(${Math.round(c.red * 255)},${Math.round(c.green * 255)},${Math.round(c.blue * 255)})`
        : sat.rec.color;
      families[name] = { color, coverage: sat.rec.coverage, n: 0 };
    }
    families[name].n += 1;
  }
  const names = Object.keys(families).sort((a, b) => {
    const rank = (name) => (families[name].coverage === "systematic" ? 0 : 1);
    return rank(a) - rank(b) || a.localeCompare(b);
  });
  box.innerHTML =
    `<h2>SAR fleets</h2><div class="legend-grid">` +
    names.map((name) => {
      const row = families[name];
      return `<div class="legend-row"><span class="legend-swatch" style="background:${row.color}"></span>${name}<span class="n">${row.n}</span></div>`;
    }).join("") +
    `</div>`;
  box.hidden = !state.layers.sats;
}

export function renderStatusLegend(on) {
  const box = $("hud-status");
  if (!box) return;
  if (!on) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  box.hidden = false;
  box.innerHTML =
    `<div class="status-legend">` +
    `<div class="legend-row"><span class="legend-swatch ais-context"></span>Global AIS — self-reported, not radar-verified</div>` +
    `<div class="legend-row"><span class="legend-swatch matched"></span>Radar + AIS — matched at acquisition</div>` +
    `<div class="legend-row"><span class="legend-swatch dark"></span>Dark candidate — vessel-like, transient, no public AIS</div>` +
    `<div class="legend-row"><span class="legend-swatch depri"></span>Deprioritized — not vessel-like or persistent</div>` +
    `<div class="legend-row"><span class="legend-swatch ais-only"></span>AIS-only in scene — broadcasting, not detected</div>` +
    `</div>`;
}

export function renderHudChips() {
  const box = $("hud-chips");
  const cat = state.catalog;
  const health = state.health;
  const chips = [];
  if (cat) {
    const origin = (cat.origin || "snapshot").toUpperCase();
    const when = (cat.fetched_at || "").slice(0, 16).replace("T", " ");
    chips.push(`<span class="chip">${origin}${when ? " " + when : ""}</span>`);
  }
  if (state.sceneOn) chips.push(`<span class="chip">SCENE PACKAGED</span>`);
  const ais = state.globalAis && state.globalAis.meta;
  if (ais) chips.push(aisChip(ais));
  box.innerHTML = chips.join("");
  const dot = $("status-dot");
  const fallbacks = (health && health.fallbacks) || [];
  dot.classList.toggle("amber", fallbacks.length > 0);
  dot.title = fallbacks.length ? "Fallback: " + fallbacks.join(", ") : "Primary sources";
}

function aisChip(meta) {
  const source = (meta.source || "empty").toLowerCase();
  const age = meta.age_s;
  const err = meta.last_error ? ` title="${escapeAttr(meta.last_error)}"` : "";
  let label = "AIS";
  let cls = "chip";
  if (source === "live") {
    const min = age == null ? "" : ` · ${Math.max(0, Math.round(age / 60))} MIN AGO`;
    label = `LIVE${min}`;
  } else if (source === "cached") {
    const hours = age == null ? "" : ` · ${(age / 3600).toFixed(0)} H AGO`;
    label = `CACHED${hours}`;
    if (age != null && age > 6 * 3600) {
      label = "STALE";
      cls = "chip stale";
    }
  } else if (source === "seed") {
    const stamp = (meta.fetched_at || "").replace("T", " ").slice(0, 16);
    label = stamp ? `SEED · ${stamp}Z` : "SEED";
  } else {
    label = "AIS EMPTY";
  }
  if (age != null && age > 6 * 3600 && source !== "seed") {
    cls = "chip stale";
    if (source !== "cached") label = "STALE";
  }
  return `<span class="${cls}"${err}>${label}</span>`;
}

function escapeAttr(value) {
  return String(value).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

export function updateShipDockCounts() {
  const counts = shipCounts();
  const globalBtn = $("dock-global-ais");
  const onlyBtn = $("dock-ais-only");
  if (globalBtn) globalBtn.textContent = `Global AIS ${counts.global}`;
  if (onlyBtn) onlyBtn.textContent = `AIS-only in scene ${counts.aisOnly}`;
}

export function markKattegat(on) {
  $("place-kattegat").classList.toggle("on", on);
}

export function wireDock({ onSats, onAis, onGlobalAis, onAisOnly, onDet, onKattegat }) {
  const bind = (id, key, fn) => {
    $(id).addEventListener("click", () => {
      state.layers[key] = !state.layers[key];
      $(id).classList.toggle("on", state.layers[key]);
      fn(state.layers[key]);
    });
  };
  bind("dock-sats", "sats", (on) => {
    const legend = $("legend");
    if (legend) legend.hidden = !on;
    onSats(on);
  });
  bind("dock-ais", "ais", onAis);
  bind("dock-global-ais", "globalAis", onGlobalAis);
  bind("dock-ais-only", "aisOnly", onAisOnly);
  bind("dock-det", "det", onDet);
  $("place-kattegat").addEventListener("click", onKattegat);
}

