import { getJSON } from "./api.js";
import { bindClock, coverageStart, cycleSpeed, onTick, returnToLive, togglePause } from "./clock.js";
import { dimForScene, loadAisOnly, loadGlobalShips, setAisOnlyVisible, setGlobalVisible, startShipPoll } from "./globe/ships.js";
import { closeAnalyze, isAnalyzeOpen, openAnalyze, showAnalysisOnGlobe, wireAnalyze } from "./analyze.js";
import { loadMpas, setLayerVisible, showScene } from "./globe/scene.js";
import {
  applyFleetFilter,
  clearSatelliteSelection,
  flyToSelection,
  loadSatellites,
  satelliteForFamily,
  selectSatellite,
} from "./globe/satellites.js";
import { clearSwath, drawSwathFor } from "./globe/swath.js";
import { createViewer, flyHome, pickId } from "./globe/viewer.js";
import { focusDetection, idleInspector, paintSelectedSatellite, showAisOnly, showGlobalShip, showModelCard, showSatellite } from "./panels/inspector.js";
import { markKattegat, markLegendFamily, renderHudChips, renderLegend, renderStatusLegend, updateShipDockCounts, wireDock, wireLegend } from "./panels/layers.js";
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
  await loadAisOnly();
  dimForScene();
  updateShipDockCounts();
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
  markLegendFamily(null);
}

function selectFleet(family) {
  const rec = satelliteForFamily(family);
  if (!rec) return;
  selectSatellite(rec);
  showSatellite(rec);
  drawSwathFor(rec);
  markLegendFamily(family);
  flyToSelection();
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
    onGlobalAis: setGlobalVisible,
    onAisOnly: setAisOnlyVisible,
    onDet: (on) => setLayerVisible("det", on),
    onRadar: (on) => setLayerVisible("radar", on),
    onUpload: (on) => setLayerVisible("upload", on),
    onKattegat: openKattegat,
  });
  wireAnalyze({ onShowGlobe: showAnalysisOnGlobe });
  wireLegend(selectFleet);
  document.addEventListener("keydown", (event) => {
    if (event.target.closest("input, textarea")) return;
    if (event.key === "a" || event.key === "A") {
      event.preventDefault();
      if (isAnalyzeOpen()) closeAnalyze();
      else openAnalyze();
      return;
    }
    if (event.key === "k" || event.key === "K") openKattegat();
    if (event.key === " ") {
      event.preventDefault();
      togglePause();
    }
    if (event.key === "l" || event.key === "L") returnToLive();
    if (event.key === "f" || event.key === "F") flyToSelection();
    if (event.key === "Escape") {
      if (isAnalyzeOpen()) {
        closeAnalyze();
        return;
      }
      clearSelection();
    }
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
      markLegendFamily(rec.family);
      return;
    }
    if (id && id.detection) {
      clearSatelliteSelection();
      clearSwath();
      focusDetection(id.detection);
      return;
    }
    if (id && id.globalShip) {
      clearSatelliteSelection();
      clearSwath();
      showGlobalShip(id.globalShip);
      return;
    }
    if (id && id.aisOnly) {
      clearSatelliteSelection();
      clearSwath();
      showAisOnly(id.aisOnly);
      return;
    }
    const entity = id;
    if (entity && entity.aisOnly) {
      clearSatelliteSelection();
      clearSwath();
      showAisOnly(entity.aisOnly);
      return;
    }
    clearSelection();
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
  onTick(() => {
    paintTimeline();
    paintSelectedSatellite();
  });
  try {
    const [, missions, health, model] = await Promise.all([
      loadSatellites(),
      getJSON("/api/missions"),
      getJSON("/api/health"),
      getJSON("/api/model"),
    ]);
    set({ missions: missions.missions || {}, health, model });
    await loadGlobalShips();
    await loadAisOnly();
    startShipPoll();
    updateShipDockCounts();
    renderHudChips();
    renderLegend();
    renderStatusLegend(true);
    await loadMpas();
  } catch (err) {
    console.error(err);
  }
}

main();
