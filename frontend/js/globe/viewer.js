import { state } from "../state.js";
import { $ } from "../ui/dom.js";
import { coord } from "../ui/format.js";

const cfg = window.DARKWATCH_CONFIG || {};

function imagery(mode) {
  if (mode === "vector") {
    return new Cesium.UrlTemplateImageryProvider({
      url: "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
      credit: "© OpenStreetMap contributors © CARTO",
      maximumLevel: 19,
    });
  }
  return new Cesium.UrlTemplateImageryProvider({
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    credit: "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
    maximumLevel: 19,
  });
}

function styleLayer(layer, mode) {
  if (mode === "imagery") {
    layer.brightness = 0.55;
    layer.saturation = 0.25;
    layer.contrast = 1.15;
  } else {
    layer.brightness = 1;
    layer.saturation = 1;
    layer.contrast = 1;
  }
}

export function createViewer() {
  if (cfg.ionToken) Cesium.Ion.defaultAccessToken = cfg.ionToken;
  const provider = imagery("imagery");
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
    baseLayer: new Cesium.ImageryLayer(provider),
    terrainProvider: new Cesium.EllipsoidTerrainProvider(),
  });
  const globe = viewer.scene.globe;
  globe.baseColor = Cesium.Color.fromCssColorString("#05070a");
  globe.enableLighting = true;
  globe.showGroundAtmosphere = true;
  viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#05070a");
  viewer.scene.fog.enabled = false;
  viewer.scene.skyAtmosphere.brightnessShift = -0.25;
  viewer.scene.skyAtmosphere.saturationShift = -0.35;
  viewer.scene.skyBox.show = true;
  styleLayer(viewer.imageryLayers.get(0), "imagery");
  viewer.camera.setView({ destination: Cesium.Cartesian3.fromDegrees(8, 20, 18000000) });
  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  handler.setInputAction((move) => {
    const picked = viewer.scene.pick(move.endPosition);
    const tip = $("hud-tip");
    if (picked && picked.id && picked.id.satellite) {
      const rec = picked.id.satellite;
      const sat = state.sats.find((item) => item.rec.norad === rec.norad);
      const alt = sat && sat.altKm != null ? `  ${sat.altKm.toFixed(0)} km` : "";
      tip.hidden = false;
      tip.textContent = `${rec.name}  ${rec.family}${alt}`;
    } else {
      tip.hidden = true;
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
  state.viewer.camera.flyTo({
    destination: dest,
    duration,
    easingFunction: Cesium.EasingFunction.CUBIC_IN_OUT,
  });
}

export function setBasemap(mode) {
  const viewer = state.viewer;
  const layer = viewer.imageryLayers.get(0);
  viewer.imageryLayers.remove(layer, true);
  const next = viewer.imageryLayers.addImageryProvider(imagery(mode), 0);
  styleLayer(next, mode);
}

export function pickOcean(click, onPoint) {
  const viewer = state.viewer;
  const picked = viewer.scene.pick(click.position);
  if (picked && picked.id && (picked.id.satellite || picked.id.detection)) return;
  const cartesian = viewer.camera.pickEllipsoid(click.position, Cesium.Ellipsoid.WGS84);
  if (!cartesian) return;
  const carto = Cesium.Cartographic.fromCartesian(cartesian);
  onPoint(Cesium.Math.toDegrees(carto.latitude), Cesium.Math.toDegrees(carto.longitude));
}
