import { getJSON } from "./api.js";
import { bindClock, coverageStart, cycleSpeed, onTick, returnToLive, togglePause } from "./clock.js";
import { loadMpas, setLayerVisible, showScene } from "./globe/scene.js";
import {
  applyFleetFilter,
  clearSatelliteSelection,
  flyToSelection,
  loadSatellites,
  selectSatellite,
} from "./globe/satellites.js";
import { clearSwath, drawSwathFor } from "./globe/swath.js";
import { createViewer, flyHome, pickId } from "./globe/viewer.js";
import { focusDetection, idleInspector, showModelCard, showSatellite } from "./panels/inspector.js";
import { markKattegat, renderHudChips, renderLegend, renderStatusLegend, wireDock } from "./panels/layers.js";
import { set } from "./state.js";
import { bindScrub, drawTimeline, paint as paintTimeline } from "./timeline.js";
import { $ } from "./ui/dom.js";

async function loadCoverage(lat, lon, title) {
  try {
    const start = coverageStart();
    const data = await getJSON(
      `/api/coverage?lat=${lat}&lon=${lon}&hours=48&start=${encodeURIComponent(start.toISOString())}`,
    );
    $("timeline").hidden = false;
    drawTimeline(data, title);
  } catch (err) {
    $("timeline").hidden = true;
    console.warn(err);
  }
}

async function openKattegat() {
  const data = await getJSON("/api/regions");
  const region = (data.regions || []).find((row) => row.id === "kattegat");
  if (!region) return;
  set({ region, selectedPoint: { lat: region.lat, lon: region.lon } });
  markKattegat(true);
  await showScene();
  await loadCoverage(region.lat, region.lon, "Kattegat · 48 h");
  renderHudChips();
  renderStatusLegend(true);
}

function showEarth() {
  flyHome();
}

function clearSelection() {
  clearSatelliteSelection();
  clearSwath();
  idleInspector();
}

function wire() {
  $("wordmark").addEventListener("click", showEarth);
  $("speed").addEventListener("click", cycleSpeed);
  $("live").addEventListener("click", returnToLive);
  $("card-close").addEventListener("click", clearSelection);
  $("dock-model").addEventListener("click", () => {
    clearSatelliteSelection();
    clearSwath();
    showModelCard();
  });
  wireDock({
    onSats: applyFleetFilter,
    onAis: (on) => setLayerVisible("ais", on),
    onDet: (on) => setLayerVisible("det", on),
    onKattegat: openKattegat,
  });
  document.addEventListener("keydown", (event) => {
    if (event.target.closest("input, textarea")) return;
    if (event.key === "k" || event.key === "K") openKattegat();
    if (event.key === " ") {
      event.preventDefault();
      togglePause();
    }
    if (event.key === "l" || event.key === "L") returnToLive();
    if (event.key === "f" || event.key === "F") flyToSelection();
    if (event.key === "Escape") clearSelection();
    if (event.key === "?") $("shortcuts").showModal();
  });
}

async function main() {
  wire();
  bindScrub();
  const viewer = createViewer();
  set({ viewer });
  bindClock(viewer);
  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  handler.setInputAction((click) => {
    const id = pickId(click);
    if (id && id.satellite) {
      const rec = id.satellite;
      selectSatellite(rec);
      showSatellite(rec);
      drawSwathFor(rec);
      return;
    }
    if (id && id.detection) {
      clearSatelliteSelection();
      clearSwath();
      focusDetection(id.detection);
      return;
    }
    clearSelection();
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
  onTick(() => {
    paintTimeline();
  });
  try {
    const [, missions, health, model] = await Promise.all([
      loadSatellites(),
      getJSON("/api/missions"),
      getJSON("/api/health"),
      getJSON("/api/model"),
    ]);
    set({ missions: missions.missions || {}, health, model });
    renderHudChips();
    renderLegend();
    await loadMpas();
  } catch (err) {
    console.error(err);
  }
}

main();
