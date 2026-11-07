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
  box.innerHTML = chips.join("");
  const dot = $("status-dot");
  const fallbacks = (health && health.fallbacks) || [];
  dot.classList.toggle("amber", fallbacks.length > 0);
  dot.title = fallbacks.length ? "Fallback: " + fallbacks.join(", ") : "Primary sources";
}

export function markKattegat(on) {
  $("place-kattegat").classList.toggle("on", on);
}

export function wireDock({ onSats, onAis, onDet, onKattegat }) {
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
  bind("dock-det", "det", onDet);
  $("place-kattegat").addEventListener("click", onKattegat);
}

