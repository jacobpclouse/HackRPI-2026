import { getJSON } from "../api.js";
import { set, state } from "../state.js";
import { $, esc } from "../ui/dom.js";

export async function loadRegions(onSelect) {
  const data = await getJSON("/api/regions");
  const box = $("regions");
  box.innerHTML = "";
  for (const region of data.regions) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "region";
    btn.dataset.id = region.id;
    btn.innerHTML = `<strong>${esc(region.name)}</strong><small>${esc(region.blurb)}</small>`;
    btn.addEventListener("click", () => {
      document.querySelectorAll(".region").forEach((el) => el.classList.remove("active"));
      btn.classList.add("active");
      onSelect(region);
    });
    box.appendChild(btn);
  }
}

export function markRegion(id) {
  document.querySelectorAll(".region").forEach((el) => el.classList.toggle("active", el.dataset.id === id));
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
  chips.push(`<span class="chip">SCENE PACKAGED</span>`);
  chips.push(`<span class="chip">${state.clockLive ? "LIVE" : "SIM"}</span>`);
  box.innerHTML = chips.join("");
  const dot = $("status-dot");
  const fallbacks = (health && health.fallbacks) || [];
  dot.classList.toggle("amber", fallbacks.length > 0);
  dot.title = fallbacks.length ? "Fallback: " + fallbacks.join(", ") : "Primary sources";
}

export function setMode(mode) {
  set({ mode });
  document.querySelectorAll(".modes button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });
}

export function wireLayerToggles({ onSats, onMpa, onAis, onDet, onPossible }) {
  $("toggle-sats").addEventListener("change", (event) => {
    state.layers.sats = event.target.checked;
    onSats();
  });
  $("toggle-mpa").addEventListener("change", (event) => {
    state.layers.mpa = event.target.checked;
    onMpa(event.target.checked);
  });
  $("toggle-ais").addEventListener("change", (event) => {
    state.layers.ais = event.target.checked;
    onAis(event.target.checked);
  });
  $("toggle-det").addEventListener("change", (event) => {
    state.layers.det = event.target.checked;
    onDet(event.target.checked);
  });
  $("toggle-possible").addEventListener("change", (event) => {
    state.layers.possible = event.target.checked;
    onPossible(event.target.checked);
  });
}
