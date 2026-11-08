import { getJSON } from "../api.js";
import { set, state } from "../state.js";

const ZOOM_ARROWS_M = 1.5e6;
const ARROW_CAP = 1500;
const POLL_MS = 120000;
const SCALE = new Cesium.NearFarScalar(8.0e5, 1.4, 1.8e7, 0.35);

let aisColor = Cesium.Color.fromCssColorString("#9fb3c8");
let points = null;
let arrows = null;
let arrowTex = null;
let aisOnly = [];
let rows = [];
let fetchedAt = null;
let excluded = null;
let pollTimer = null;
let preRenderRemove = null;
const occluder = new Cesium.EllipsoidalOccluder(Cesium.Ellipsoid.WGS84, Cesium.Cartesian3.ZERO);

function tokenColor() {
  const raw = getComputedStyle(document.documentElement).getPropertyValue("--ais-context").trim();
  return Cesium.Color.fromCssColorString(raw || "#9fb3c8");
}

function arrowCanvas() {
  const canvas = document.createElement("canvas");
  canvas.width = 16;
  canvas.height = 16;
  const g = canvas.getContext("2d");
  g.fillStyle = aisColor.toCssColorString();
  g.beginPath();
  g.moveTo(8, 1);
  g.lineTo(13, 14);
  g.lineTo(8, 10);
  g.lineTo(3, 14);
  g.closePath();
  g.fill();
  return canvas;
}

function inExcluded(lat, lon) {
  if (!excluded || excluded.length < 4) return false;
  const [west, south, east, north] = excluded;
  return lat >= south && lat <= north && lon >= west && lon <= east;
}

function alpha() {
  if (!state.layers.globalAis) return 0;
  return state.sceneOn ? 0.35 : 1;
}

function ensureCollections() {
  const scene = state.viewer.scene;
  aisColor = tokenColor();
  if (!points) {
    points = scene.primitives.add(new Cesium.PointPrimitiveCollection({
      blendOption: Cesium.BlendOption.OPAQUE,
    }));
  }
  if (!arrows) {
    arrows = scene.primitives.add(new Cesium.BillboardCollection());
    arrowTex = arrowCanvas();
  }
}

function headingOf(ship) {
  const h = ship.heading;
  if (h != null && h !== 511 && Number.isFinite(Number(h))) return Number(h);
  const c = ship.cog;
  if (c != null && Number.isFinite(Number(c))) return Number(c);
  return null;
}

function applyPoints(ships) {
  ensureCollections();
  points.removeAll();
  arrows.removeAll();
  rows = [];
  const color = aisColor.withAlpha(alpha());
  for (const ship of ships) {
    if (inExcluded(ship.lat, ship.lon)) continue;
    const cartesian = Cesium.Cartesian3.fromDegrees(ship.lon, ship.lat);
    const pt = points.add({
      position: cartesian,
      color,
      pixelSize: 3,
      scaleByDistance: SCALE,
    });
    pt.id = { globalShip: ship };
    const hdg = headingOf(ship);
    const bill = arrows.add({
      position: cartesian,
      image: arrowTex,
      width: 10,
      height: 10,
      rotation: hdg == null ? 0 : Cesium.Math.toRadians(-hdg),
      alignedAxis: Cesium.Cartesian3.UNIT_Z,
      color,
      show: false,
    });
    bill.id = { globalShip: ship };
    rows.push({ ship, point: pt, arrow: bill, cartesian });
  }
  points.show = state.layers.globalAis;
  arrows.show = false;
}

function updateArrowVisibility() {
  if (!rows.length) return;
  const on = state.layers.globalAis;
  const height = state.viewer.camera.positionCartographic.height;
  const zoomed = on && height < ZOOM_ARROWS_M;
  if (arrows) arrows.show = zoomed;
  occluder.cameraPosition = state.viewer.camera.position;
  let shown = 0;
  for (const row of rows) {
    const visible = on && occluder.isPointVisible(row.cartesian);
    row.point.show = visible;
    if (!zoomed || shown >= ARROW_CAP) {
      row.arrow.show = false;
      continue;
    }
    row.arrow.show = visible;
    if (visible) shown += 1;
  }
}

export function setGlobalVisible(on) {
  if (points) points.show = on;
  const color = aisColor.withAlpha(alpha());
  for (const row of rows) {
    row.point.color = color;
    row.arrow.color = color;
  }
  updateArrowVisibility();
}

export function setAisOnlyVisible(on) {
  for (const entity of aisOnly) entity.show = on;
}

export function dimForScene() {
  setGlobalVisible(state.layers.globalAis);
}

function setAisOnly(collection) {
  for (const entity of aisOnly) state.viewer.entities.remove(entity);
  aisOnly = [];
  if (!collection || !collection.features) return;
  const show = state.layers.aisOnly;
  for (const feature of collection.features) {
    const [lon, lat] = feature.geometry.coordinates;
    const entity = state.viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(lon, lat),
      show,
      ellipse: {
        semiMinorAxis: 280,
        semiMajorAxis: 280,
        material: Cesium.Color.TRANSPARENT,
        outline: true,
        outlineColor: aisColor,
        height: 0,
      },
      point: {
        pixelSize: 4,
        color: Cesium.Color.TRANSPARENT,
        outlineColor: aisColor,
        outlineWidth: 1,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
    entity.aisOnly = feature;
    aisOnly.push(entity);
  }
}

export async function loadAisOnly() {
  try {
    const data = await getJSON("/api/scene/ais_only");
    setAisOnly(data);
    set({ aisOnly: data });
    return data;
  } catch (err) {
    console.warn(err);
    return null;
  }
}

export async function loadGlobalShips() {
  try {
    const data = await getJSON("/api/ships/global");
    excluded = (data.meta && data.meta.excluded_bbox) || excluded;
    if (data.fetched_at && data.fetched_at === fetchedAt && rows.length) {
      set({ globalAis: data });
      return data;
    }
    const fields = data.fields || [];
    const ships = (data.rows || []).map((row) => {
      const item = {};
      fields.forEach((name, i) => { item[name] = row[i]; });
      return item;
    });
    applyPoints(ships);
    fetchedAt = data.fetched_at;
    set({ globalAis: data });
    return data;
  } catch (err) {
    console.warn(err);
    return state.globalAis;
  }
}

export function startShipPoll() {
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    loadGlobalShips();
  }, POLL_MS);
  if (!preRenderRemove) {
    preRenderRemove = state.viewer.scene.preRender.addEventListener(updateArrowVisibility);
  }
}

export function shipCounts() {
  return {
    global: rows.length,
    aisOnly: aisOnly.length,
  };
}
