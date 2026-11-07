import { getJSON } from "../api.js";
import { set, state } from "../state.js";
import { $ } from "../ui/dom.js";

const layers = { scene: null, tracks: [], dets: [], mpas: null, pick: null };

export function markPoint(lat, lon, name) {
  if (layers.pick) state.viewer.entities.remove(layers.pick);
  layers.pick = state.viewer.entities.add({
    position: Cesium.Cartesian3.fromDegrees(lon, lat),
    point: { pixelSize: 8, color: Cesium.Color.WHITE, outlineColor: Cesium.Color.BLACK, outlineWidth: 1 },
    label: {
      text: name,
      font: "12px Inter, sans-serif",
      pixelOffset: new Cesium.Cartesian2(0, -16),
      fillColor: Cesium.Color.WHITE,
      disableDepthTestDistance: Number.POSITIVE_INFINITY,
    },
  });
}

export async function loadMpas() {
  const data = await getJSON("/api/mpas");
  if (!data.features || !data.features.length) return;
  const ds = await Cesium.GeoJsonDataSource.load(data, {
    stroke: Cesium.Color.fromCssColorString("#9b8afb"),
    fill: Cesium.Color.TRANSPARENT,
    strokeWidth: 1,
    clampToGround: true,
  });
  await state.viewer.dataSources.add(ds);
  layers.mpas = ds;
}

export function setLayerVisible(name, on) {
  if (name === "mpa" && layers.mpas) layers.mpas.show = on;
  if (name === "ais") for (const entity of layers.tracks) entity.show = on;
  if (name === "det") for (const entity of layers.dets) entity.show = on;
}

export async function clearSceneLayers() {
  const viewer = state.viewer;
  if (layers.scene) {
    viewer.imageryLayers.remove(layers.scene, true);
    layers.scene = null;
  }
  for (const entity of layers.tracks) viewer.entities.remove(entity);
  for (const entity of layers.dets) viewer.entities.remove(entity);
  layers.tracks = [];
  layers.dets = [];
  set({ sceneOn: false });
}

function addDetections(collection) {
  const show = $("toggle-det").checked;
  for (const feature of collection.features) {
    const [lon, lat] = feature.geometry.coordinates;
    const matched = feature.properties.matched;
    const color = Cesium.Color.fromCssColorString(matched ? "#3dd68c" : "#ff4d4f");
    const entity = state.viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(lon, lat),
      show,
      ellipse: {
        semiMinorAxis: matched ? 450 : 700,
        semiMajorAxis: matched ? 450 : 700,
        material: Cesium.Color.TRANSPARENT,
        outline: true,
        outlineColor: color,
        height: 0,
      },
      label: {
        text: feature.properties.id,
        font: "11px JetBrains Mono, monospace",
        fillColor: color,
        pixelOffset: new Cesium.Cartesian2(0, -16),
        show: !matched,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
    entity.detection = feature;
    layers.dets.push(entity);
  }
}

function addTracks(collection) {
  const show = $("toggle-ais").checked;
  for (const feature of collection.features) {
    const flat = [];
    for (const pair of feature.geometry.coordinates) flat.push(pair[0], pair[1]);
    if (flat.length < 4) continue;
    const entity = state.viewer.entities.add({
      show,
      polyline: {
        positions: Cesium.Cartesian3.fromDegreesArray(flat),
        width: 1,
        material: Cesium.Color.fromCssColorString("#8a94a3").withAlpha(0.7),
        clampToGround: true,
      },
    });
    layers.tracks.push(entity);
  }
}

export async function showScene() {
  const scene = await getJSON("/api/scene");
  const [west, south, east, north] = scene.meta.bbox;
  const rect = Cesium.Rectangle.fromDegrees(west, south, east, north);
  state.viewer.camera.flyTo({ destination: rect, duration: 2.5, easingFunction: Cesium.EasingFunction.CUBIC_IN_OUT });
  await clearSceneLayers();
  const provider = await Cesium.SingleTileImageryProvider.fromUrl("/api/scene/preview.png", { rectangle: rect });
  layers.scene = state.viewer.imageryLayers.addImageryProvider(provider);
  const dets = await getJSON("/api/detections");
  const ais = await getJSON("/api/ais");
  addDetections(dets);
  addTracks(ais);
  set({ sceneOn: true });
  return { scene, dets };
}
