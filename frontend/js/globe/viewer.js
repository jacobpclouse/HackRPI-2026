import { hoverDetection } from "./scene.js";
import { state } from "../state.js";
import { $ } from "../ui/dom.js";
import { coord } from "../ui/format.js";

const cfg = window.DARKWATCH_CONFIG || {};

function esriImagery() {
  return new Cesium.UrlTemplateImageryProvider({
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    credit: "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
    maximumLevel: 19,
  });
}

function gradeLayer(layer) {
  layer.brightness = 1.02;
  layer.saturation = 0.92;
  layer.contrast = 1.04;
}

export function createViewer() {
  if (cfg.ionToken) Cesium.Ion.defaultAccessToken = cfg.ionToken;
  const viewer = new Cesium.Viewer("cesium", {
    animation: false,
    timeline: false,
    baseLayerPicker: false,
    geocoder: false,
    homeButton: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    fullscreenButton: false,
    infoBox: false,
    selectionIndicator: false,
    baseLayer: false,
    terrainProvider: new Cesium.EllipsoidTerrainProvider(),
  });
  const esri = viewer.imageryLayers.addImageryProvider(esriImagery());
  gradeLayer(esri);
  const globe = viewer.scene.globe;
  globe.baseColor = Cesium.Color.fromCssColorString("#0a1628");
  globe.show = true;
  globe.enableLighting = true;
  globe.showGroundAtmosphere = true;
  if (typeof globe.atmosphereLightIntensity === "number") {
    globe.atmosphereLightIntensity = 12;
  }
  globe.lightingFadeOutDistance = 2.4e7;
  globe.lightingFadeInDistance = 4.0e7;
  globe.nightFadeOutDistance = 1.0e7;
  globe.nightFadeInDistance = 3.0e7;
  viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#05070a");
  viewer.scene.fog.enabled = false;
  viewer.scene.skyAtmosphere.brightnessShift = -0.08;
  viewer.scene.skyAtmosphere.saturationShift = -0.12;
  viewer.scene.skyBox.show = true;
  viewer.camera.setView({ destination: Cesium.Cartesian3.fromDegrees(-40, 18, 18000000) });
  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  handler.setInputAction((move) => {
    const picked = viewer.scene.pick(move.endPosition);
    const rec = picked && picked.id && picked.id.satellite;
    const det = picked && picked.id && picked.id.detection;
    const globalShip = picked && picked.id && picked.id.globalShip;
    const aisOnly = picked && picked.id && picked.id.aisOnly;
    const tip = $("hud-tip");
    if (rec) {
      const sat = state.sats.find((item) => item.rec.norad === rec.norad);
      const alt = sat && sat.altKm != null ? `  ${sat.altKm.toFixed(0)} km` : "";
      tip.hidden = false;
      tip.textContent = `${rec.name}  ${rec.family}${alt}`;
      hoverDetection(null);
    } else if (det) {
      tip.hidden = false;
      const status = det.properties.candidate_status
        || (det.properties.matched ? "matched" : "unreviewed");
      tip.textContent = `${det.properties.id}  ${status.replace("_", " ")}`;
      hoverDetection(det);
    } else if (globalShip) {
      tip.hidden = false;
      tip.textContent = `${globalShip.name || globalShip.mmsi}  AIS`;
      hoverDetection(null);
    } else if (aisOnly) {
      const p = aisOnly.properties || aisOnly;
      tip.hidden = false;
      tip.textContent = `${p.name || p.mmsi}  AIS-only`;
      hoverDetection(null);
    } else {
      tip.hidden = true;
      hoverDetection(null);
    }
    const cartesian = viewer.camera.pickEllipsoid(move.endPosition, Cesium.Ellipsoid.WGS84);
    if (!cartesian) {
      $("hud-cursor").textContent = "—";
      return;
    }
    const carto = Cesium.Cartographic.fromCartesian(cartesian);
    $("hud-cursor").textContent = coord(
      Cesium.Math.toDegrees(carto.latitude),
      Cesium.Math.toDegrees(carto.longitude),
    );
  }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);
  viewer.scene.postRender.addEventListener(() => {
    const height = viewer.camera.positionCartographic.height;
    $("hud-alt").textContent = height > 1000
      ? `ALT ${(height / 1000).toFixed(0)} km`
      : `ALT ${height.toFixed(0)} m`;
  });
  return viewer;
}

export function flyTo(dest, duration = 2.5) {
  state.viewer.trackedEntity = undefined;
  state.viewer.camera.flyTo({
    destination: dest,
    duration,
    easingFunction: Cesium.EasingFunction.CUBIC_IN_OUT,
  });
}

export function flyHome() {
  flyTo(Cesium.Cartesian3.fromDegrees(-40, 18, 18000000));
}

export function pickId(click) {
  const pos = click.position || click.endPosition;
  if (!pos) return null;
  const picked = state.viewer.scene.pick(pos);
  return (picked && picked.id) || null;
}
