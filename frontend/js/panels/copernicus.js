import { ensureShipOverlays, setShipGate } from "../globe/scene.js";
import { hideImagery, setAppearance, showAcquisition } from "../globe/copernicus.js";
import { state } from "../state.js";
import { $ } from "../ui/dom.js";

const MAX_SPAN = 12;

let open = false;
let configured = false;
let rows = [];
let selected = null;
let searching = 0;

function dayStamp(date) {
  return date.toISOString().slice(0, 10);
}

function setStatus(text) {
  $("sar-status").textContent = text;
}

function appearanceFromInputs() {
  const brightness = Number($("sar-bright").value);
  const contrast = Number($("sar-contrast").value);
  const gamma = Number($("sar-gamma").value);
  const alpha = Number($("sar-opacity").value);
  $("sar-bright-val").textContent = brightness.toFixed(2);
  $("sar-contrast-val").textContent = contrast.toFixed(2);
  $("sar-gamma-val").textContent = gamma.toFixed(2);
  $("sar-opacity-val").textContent = alpha.toFixed(2);
  setAppearance({ brightness, contrast, gamma, alpha });
}

function viewTooWide(box) {
  return box.east - box.west > MAX_SPAN || box.north - box.south > MAX_SPAN;
}

function viewBox() {
  const rect = state.viewer.camera.computeViewRectangle(Cesium.Ellipsoid.WGS84);
  if (!rect) return null;
  const west = Cesium.Math.toDegrees(rect.west);
  const south = Cesium.Math.toDegrees(rect.south);
  const east = Cesium.Math.toDegrees(rect.east);
  const north = Cesium.Math.toDegrees(rect.north);
  if (!(east > west)) return null;
  return {
    west,
    south: Math.max(-85, south),
    east,
    north: Math.min(85, north),
  };
}

function fillSelect(select, items, selectedId) {
  select.replaceChildren();
  for (const item of items) {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.label;
    select.appendChild(option);
  }
  if (selectedId) select.value = selectedId;
}

function paintAcquisition() {
  const stamp = $("sar-stamp");
  const ships = $("sar-ships");
  const key = $("sar-key");
  const viz = $("sar-viz");
  if (!selected) {
    stamp.textContent = "";
    ships.textContent = "";
    key.hidden = true;
    viz.replaceChildren();
    hideImagery();
    setShipGate("follow");
    return;
  }
  const visualizations = selected.visualizations || [];
  const current = visualizations.some((row) => row.id === viz.value) ? viz.value : (visualizations[0] && visualizations[0].id);
  fillSelect(viz, visualizations, current);
  stamp.textContent = selected.datetime ? `Acquisition ${selected.datetime}` : "";
  const ship = selected.ships || { available: false, note: "" };
  ships.textContent = ship.note || "";
  key.hidden = !ship.available;
  setShipGate(ship.available ? "follow" : "hide");
  if (ship.available) ensureShipOverlays().catch(() => {});
  if ($("sar-show").checked && current) {
    showAcquisition(selected, current, {
      onLoading: () => setStatus(`Loading ${selected.datetime}…`),
      onReady: () => setStatus(`Showing ${selected.datetime}.`),
      onMiss: () => setStatus("This pass does not cover the current view."),
      onError: () => setStatus("This pass did not render. The Esri map stays visible."),
    });
  } else {
    hideImagery();
    if (!visualizations.length) {
      setStatus("This acquisition did not report a supported polarization, so it is not rendered.");
    } else {
      setStatus(`Acquisition ${selected.datetime}. Imagery layer is off.`);
    }
  }
}

async function search(lookbackDays = 0) {
  if (!open || !configured) return;
  const box = viewBox();
  if (!box) {
    setStatus("Move the globe so the view does not cross the antimeridian, then search again.");
    return;
  }
  if (viewTooWide(box)) {
    setStatus("Zoom in first. A wide view covers many passes, and ships move between them.");
    return;
  }
  const day = $("sar-day").value;
  if (!day) {
    setStatus("Pick the UTC day of the pass.");
    return;
  }
  const seq = ++searching;
  setStatus(lookbackDays ? "Looking for the latest pass in this view…" : "Loading passes for this day…");
  const end = `${day}T23:59:59Z`;
  const startDate = new Date(`${day}T00:00:00Z`);
  startDate.setUTCDate(startDate.getUTCDate() - lookbackDays);
  const start = `${dayStamp(startDate)}T00:00:00Z`;
  let payload;
  try {
    const response = await fetch("/api/copernicus/acquisitions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...box, start, end }),
    });
    payload = await response.json();
  } catch {
    if (seq !== searching) return;
    setStatus("Acquisitions could not be loaded.");
    return;
  }
  if (seq !== searching) return;
  configured = payload.configured !== false;
  if (payload.state === "unconfigured") {
    configured = false;
    $("sar-controls").hidden = true;
    rows = [];
    selected = null;
    hideImagery();
    setShipGate("follow");
    setStatus(payload.message || "Copernicus imagery is not configured.");
    return;
  }
  if (payload.state === "unavailable") {
    rows = [];
    selected = null;
    paintAcquisition();
    setStatus(payload.message || "Copernicus imagery is unavailable.");
    return;
  }
  rows = payload.acquisitions || [];
  if (lookbackDays && rows.length) {
    const passDay = rows[0].datetime.slice(0, 10);
    $("sar-day").value = passDay;
    rows = rows.filter((row) => row.datetime.slice(0, 10) === passDay);
  }
  if (!rows.length) {
    selected = null;
    paintAcquisition();
    setStatus(payload.message || "No Sentinel-1 coverage in this view.");
    return;
  }
  const keep = rows.find((row) => selected && row.id === selected.id);
  selected = keep || rows[0];
  fillSelect(
    $("sar-when"),
    rows.map((row) => ({
      id: row.id,
      label: `${row.datetime}${row.platform ? " · " + row.platform : ""}${row.orbit ? " · " + row.orbit : ""}`,
    })),
    selected.id,
  );
  paintAcquisition();
  if (payload.truncated) {
    setStatus(`${$("sar-status").textContent} Showing the 100 most recent acquisitions.`);
  }
}

async function openPanel() {
  open = true;
  $("sar").hidden = false;
  $("dock-sar").classList.add("on");
  $("sar-day").value = dayStamp(new Date());
  setStatus("Checking Copernicus…");
  try {
    const response = await fetch("/api/copernicus/status");
    const payload = await response.json();
    configured = Boolean(payload.configured);
    if (!configured) {
      $("sar-controls").hidden = true;
      setStatus(payload.message || "Copernicus imagery is not configured.");
      return;
    }
  } catch {
    configured = false;
    $("sar-controls").hidden = true;
    setStatus("Copernicus status could not be loaded.");
    return;
  }
  $("sar-controls").hidden = false;
  appearanceFromInputs();
  setStatus("Zoom in, then search this view for one UTC day.");
}

function closePanel() {
  open = false;
  searching += 1;
  $("sar").hidden = true;
  $("dock-sar").classList.remove("on");
  rows = [];
  selected = null;
  hideImagery();
  setShipGate("follow");
}

export function bindCopernicus() {
  $("dock-sar").addEventListener("click", () => {
    if (open) closePanel();
    else openPanel();
  });
  $("sar-close").addEventListener("click", closePanel);
  $("sar-search").addEventListener("click", () => search(0));
  $("sar-latest").addEventListener("click", () => search(12));
  $("sar-when").addEventListener("change", () => {
    selected = rows.find((row) => row.id === $("sar-when").value) || null;
    paintAcquisition();
  });
  $("sar-viz").addEventListener("change", paintAcquisition);
  $("sar-show").addEventListener("change", paintAcquisition);
  for (const id of ["sar-bright", "sar-contrast", "sar-gamma", "sar-opacity"]) {
    $(id).addEventListener("input", appearanceFromInputs);
  }
}
