import { getJSON } from "./api.js";
import { bindClock, coverageStart, cycleSpeed, onTick, returnToLive, togglePause } from "./clock.js";
import { loadMpas, markPoint, setLayerVisible } from "./globe/scene.js";
import {
  applyFleetFilter,
  clearSatelliteSelection,
  flyToSelection,
  loadSatellites,
  selectSatellite,
  updateSatellites,
} from "./globe/satellites.js";
import { clearSwath, drawSwathFor } from "./globe/swath.js";
import { createViewer, flyTo, pickOcean, setBasemap } from "./globe/viewer.js";
import { playNarration } from "./narration.js";
import { idleInspector, renderAnalysis, renderPassDetail, renderScenePanel, showSatellite } from "./panels/inspector.js";
import { loadRegions, markRegion, renderHudChips, setMode, wireLayerToggles } from "./panels/layers.js";
import { set, state } from "./state.js";
import { bindScrub, drawTimeline, paint as paintTimeline } from "./timeline.js";
import { $ } from "./ui/dom.js";

function bootOverlay() {
  const el = $("boot");
  const log = $("boot-log");
  const skip = sessionStorage.getItem("darkwatch-booted");
  if (skip) return { line() {}, done() {} };
  el.hidden = false;
  const line = (text) => {
    const li = document.createElement("li");
    li.textContent = text;
    log.appendChild(li);
  };
  const hide = () => {
    el.hidden = true;
    sessionStorage.setItem("darkwatch-booted", "1");
  };
  const onKey = () => {
    hide();
    window.removeEventListener("keydown", onKey);
  };
  window.addEventListener("keydown", onKey);
  return { line, done: hide };
}

async function loadCoverage(lat, lon, title) {
  $("tl-title").textContent = "Computing passes for " + title;
  $("tl-gap").textContent = "";
  try {
    const start = coverageStart();
    const data = await getJSON(
      `/api/coverage?lat=${lat}&lon=${lon}&hours=48&start=${encodeURIComponent(start.toISOString())}`,
    );
    drawTimeline(data, "Next 48 h · " + title);
    renderPassDetail(data);
  } catch (err) {
    $("tl-title").textContent = "Pass prediction failed";
    $("tl-note").textContent = err.message;
  }
}

async function selectRegion(region) {
  set({ region, selectedPoint: { lat: region.lat, lon: region.lon } });
  markPoint(region.lat, region.lon, region.name);
  flyTo(Cesium.Cartesian3.fromDegrees(region.lon, region.lat, 1800000));
  setMode("coverage");
  await loadCoverage(region.lat, region.lon, region.name);
}

async function enterMode(mode) {
  setMode(mode);
  if (mode === "orbit") {
    flyTo(Cesium.Cartesian3.fromDegrees(10, 18, 18000000));
    idleInspector();
    return;
  }
  if (mode === "coverage") {
    if (state.region) await selectRegion(state.region);
    else idleInspector();
    return;
  }
  if (mode === "scene") {
    if (!state.region || state.region.id !== "kattegat") {
      const btn = [...document.querySelectorAll(".region")].find((el) => el.dataset.id === "kattegat");
      if (btn) btn.click();
    }
    await renderScenePanel();
    return;
  }
  if (mode === "analysis") {
    const story = await renderAnalysis();
    if (story && story.scene_day) {
      const day = story.scene_day;
      day.observed = story.observed_acquisition.time;
      drawTimeline(day, "2 Nov 2026 · Kattegat scene day");
    }
  }
}

function wire() {
  document.querySelectorAll(".modes button").forEach((btn) => {
    btn.addEventListener("click", () => enterMode(btn.dataset.mode));
  });
  $("narrate").addEventListener("click", () => playNarration("opening"));
  $("basemap").addEventListener("click", () => {
    const next = state.basemap === "imagery" ? "vector" : "imagery";
    set({ basemap: next });
    $("basemap").textContent = next === "imagery" ? "Imagery" : "Vector";
    setBasemap(next);
  });
  $("speed").addEventListener("click", cycleSpeed);
  $("live").addEventListener("click", returnToLive);
  wireLayerToggles({
    onSats: applyFleetFilter,
    onMpa: (on) => setLayerVisible("mpa", on),
    onAis: (on) => setLayerVisible("ais", on),
    onDet: (on) => setLayerVisible("det", on),
    onPossible: () => {
      if (state.coverage) paintTimeline();
    },
  });
  document.addEventListener("keydown", (event) => {
    if (event.target.closest("input, textarea")) return;
    if (event.key === "1") enterMode("orbit");
    if (event.key === "2") enterMode("coverage");
    if (event.key === "3") enterMode("scene");
    if (event.key === "4") enterMode("analysis");
    if (event.key === " ") {
      event.preventDefault();
      togglePause();
    }
    if (event.key === "l" || event.key === "L") returnToLive();
    if (event.key === "f" || event.key === "F") flyToSelection();
    if (event.key === "Escape") {
      clearSatelliteSelection();
      clearSwath();
      idleInspector();
    }
    if (event.key === "[") document.getElementById("app").classList.toggle("rail-collapsed");
    if (event.key === "]") document.getElementById("app").classList.toggle("inspector-collapsed");
    if (event.key === "?") $("shortcuts").showModal();
  });
}

async function main() {
  const boot = bootOverlay();
  wire();
  bindScrub();
  try {
    const viewer = createViewer();
    set({ viewer });
    bindClock(viewer);
    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction((click) => {
      const picked = viewer.scene.pick(click.position);
      if (picked && picked.id && picked.id.satellite) {
        const rec = picked.id.satellite;
        selectSatellite(rec);
        showSatellite(rec);
        drawSwathFor(rec);
        return;
      }
      if (picked && picked.id && picked.id.detection) return;
      pickOcean(click, (lat, lon) => {
        const region = {
          id: "custom",
          name: `${lat.toFixed(2)}°, ${lon.toFixed(2)}°`,
          lat,
          lon,
          has_scene: false,
          blurb: "Clicked point",
        };
        markRegion(null);
        selectRegion(region);
      });
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
    onTick((date) => {
      updateSatellites(date);
      paintTimeline();
    });
  } catch (err) {
    boot.line("CESIUM FAILED  " + err.message);
    return;
  }

  try {
    const [cat, missions, health] = await Promise.all([
      loadSatellites(),
      getJSON("/api/missions"),
      getJSON("/api/health"),
    ]);
    set({ missions: missions.missions || {}, health });
    const when = (cat.fetched_at || "").slice(0, 16).replace("T", " ");
    boot.line(`CATALOG  ${cat.count} OBJECTS  CELESTRAK ${when || cat.origin || ""}`.trim());
    const summary = health.scene_id ? await getJSON("/api/scene").catch(() => null) : null;
    if (summary) {
      boot.line(`SCENE  ${summary.meta.platform || "S1"} ${String(summary.summary.scene_time).slice(0, 16).replace("T", " ")}Z`);
      boot.line(`AIS  ${summary.summary.ais_vessels_with_pings} VESSELS`);
    }
    const integ = health.integrations || {};
    boot.line(`INTEGRATIONS  FISH AUDIO ${integ.fish_audio ? "ON" : "OFF"}  GEMINI ${integ.gemini ? "ON" : "OFF"}`);
    renderHudChips();
    await Promise.all([loadRegions(selectRegion), loadMpas()]);
  } catch (err) {
    boot.line("LOAD ERROR  " + err.message);
  }
  setTimeout(boot.done, 1200);
}

main();
