import { getJSON } from "../api.js";
import { set, state } from "../state.js";
import { toast } from "../ui/dom.js";

const layers = { scene: null, tiles: null, tracks: [], dets: [], mpas: null, upload: [] };
let tileErrors = 0;
let tilesDisabled = false;

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
  if (name === "radar" && layers.tiles) layers.tiles.show = on && !tilesDisabled;
  if (name === "upload") for (const entity of layers.upload) entity.show = on;
}

export async function clearSceneLayers() {
  const viewer = state.viewer;
  if (layers.scene) {
    viewer.imageryLayers.remove(layers.scene, true);
    layers.scene = null;
  }
  if (layers.tiles) {
    viewer.imageryLayers.remove(layers.tiles, true);
    layers.tiles = null;
  }
  for (const entity of layers.tracks) viewer.entities.remove(entity);
  for (const entity of layers.dets) viewer.entities.remove(entity);
  layers.tracks = [];
  layers.dets = [];
  set({ sceneOn: false });
}

function cssColor(tokenHex) {
  return Cesium.Color.fromCssColorString(tokenHex);
}

function ringPositions(lon, lat, radiusM, steps = 64) {
  const out = [];
  const latRad = (lat * Math.PI) / 180;
  const dlat = radiusM / 111320;
  const dlon = radiusM / (111320 * Math.max(0.2, Math.cos(latRad)));
  for (let i = 0; i <= steps; i += 1) {
    const a = (i / steps) * Math.PI * 2;
    out.push(lon + dlon * Math.sin(a), lat + dlat * Math.cos(a));
  }
  return Cesium.Cartesian3.fromDegreesArray(out);
}

function addDetections(collection) {
  const show = state.layers.det;
  const matchedC = cssColor("#3dd68c");
  const unmatchedC = cssColor("#ff4d4f");
  const depriC = cssColor("#545e6c");
  for (const feature of collection.features) {
    const [lon, lat] = feature.geometry.coordinates;
    const status = feature.properties.candidate_status
      || (feature.properties.matched ? "matched" : "unreviewed");
    const dark = status === "dark_candidate";
    const depri = status === "deprioritized";
    const matched = status === "matched";
    const color = matched ? matchedC : (depri ? depriC : unmatchedC);
    const radius = matched ? 450 : 700;
    const entity = state.viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(lon, lat),
      show,
      point: {
        pixelSize: matched ? 6 : (depri ? 5 : 9),
        color: depri || status === "unreviewed" ? Cesium.Color.TRANSPARENT : color,
        outlineColor: color,
        outlineWidth: matched ? 0 : 1,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
      ellipse: depri ? undefined : {
        semiMinorAxis: radius,
        semiMajorAxis: radius,
        material: status === "unreviewed" ? Cesium.Color.TRANSPARENT : color.withAlpha(0.12),
        outline: true,
        outlineColor: color,
        height: 0,
      },
      polyline: depri ? {
        positions: ringPositions(lon, lat, radius),
        width: 1,
        material: new Cesium.PolylineDashMaterialProperty({ color: depriC, dashLength: 10 }),
        clampToGround: true,
      } : undefined,
      label: {
        text: feature.properties.id,
        font: "11px JetBrains Mono, monospace",
        fillColor: Cesium.Color.WHITE,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 2,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
        pixelOffset: new Cesium.Cartesian2(0, -12),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        show: dark,
      },
    });
    entity.detection = feature;
    layers.dets.push(entity);
  }
}

export function hoverDetection(feature) {
  for (const entity of layers.dets) {
    if (!entity.label) continue;
    const status = entity.detection.properties.candidate_status;
    entity.label.show = status === "dark_candidate" || (feature && entity.detection === feature);
  }
}

function reviewTag(review) {
  if (!review || !review.decision) return "";
  const word = String(review.decision).split(" ")[0].toUpperCase();
  return ` · ${word}`;
}

export function setReviewTags(reviews) {
  const map = reviews || {};
  for (const entity of layers.dets) {
    if (!entity.label || !entity.detection) continue;
    const id = entity.detection.properties.id;
    entity.label.text = `${id}${reviewTag(map[id])}`;
  }
}

function addTracks(collection) {
  const show = state.layers.ais;
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
  state.viewer.trackedEntity = undefined;
  state.viewer.camera.flyTo({ destination: rect, duration: 2.5, easingFunction: Cesium.EasingFunction.CUBIC_IN_OUT });
  await clearSceneLayers();
  const provider = await Cesium.SingleTileImageryProvider.fromUrl("/api/scene/preview.png", { rectangle: rect });
  layers.scene = state.viewer.imageryLayers.addImageryProvider(provider);
  await addRadarTiles(rect);
  const dets = await getJSON("/api/detections");
  const ais = await getJSON("/api/ais");
  addDetections(dets);
  addTracks(ais);
  set({ sceneOn: true });
  return { scene, dets };
}

async function addRadarTiles(rect) {
  tileErrors = 0;
  tilesDisabled = false;
  try {
    const tiles = await getJSON("/api/scene/tiles");
    const maxLevel = Math.min(tiles.maxzoom ?? 13, 13);
    const imagery = new Cesium.UrlTemplateImageryProvider({
      url: tiles.template,
      rectangle: rect,
      minimumLevel: tiles.minzoom ?? 0,
      maximumLevel: maxLevel,
      credit: tiles.attribution || "",
    });
    imagery.errorEvent.addEventListener(() => {
      tileErrors += 1;
      if (!tilesDisabled && tileErrors > 10) {
        tilesDisabled = true;
        if (layers.tiles) layers.tiles.show = false;
        toast("Radar tiles failed to load. Showing the static preview.", "tiles");
      }
    });
    layers.tiles = state.viewer.imageryLayers.addImageryProvider(imagery);
    layers.tiles.show = state.layers.radar;
  } catch (err) {
    console.warn(err);
  }
}

export function clearUploadLayer() {
  for (const entity of layers.upload) state.viewer.entities.remove(entity);
  layers.upload = [];
}

export function showUploadDetections(analysis) {
  clearUploadLayer();
  const show = state.layers.upload;
  const dets = (analysis.detections || []).filter((d) => d.status === "vessel_like" && d.lat != null);
  for (const det of dets) {
    const ais = (det.ais && det.ais.status) || "no_ais";
    const color = ais === "matched"
      ? cssColor("#3dd68c")
      : (ais === "dark_candidate" ? cssColor("#ff4d4f") : cssColor("#e6eaf0"));
    const entity = state.viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(det.lon, det.lat),
      show,
      ellipse: {
        semiMinorAxis: 400,
        semiMajorAxis: 400,
        material: color.withAlpha(0.12),
        outline: true,
        outlineColor: color,
        height: 0,
      },
      label: {
        text: det.id,
        font: "11px JetBrains Mono, monospace",
        fillColor: Cesium.Color.WHITE,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 2,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
        pixelOffset: new Cesium.Cartesian2(0, -12),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
    entity.uploadDet = det;
    layers.upload.push(entity);
  }
  const btn = document.getElementById("dock-upload");
  if (btn) {
    btn.hidden = layers.upload.length === 0;
    btn.classList.toggle("on", show);
    btn.textContent = `Upload ${layers.upload.length}`;
  }
}
