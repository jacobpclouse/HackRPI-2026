import { getJSON } from "../api.js";
import { clockDate } from "../clock.js";
import { set, state } from "../state.js";
import { $ } from "../ui/dom.js";

const ORBIT_STEPS = 128;
const scratchRotation = new Cesium.Matrix3();
const scratchMatrix = new Cesium.Matrix4();

let points = null;
let orbitPrimitive = null;
let orbitGmst = 0;
let preRenderRemove = null;

function periodSeconds(satrec) {
  const meanMotion = satrec.no * (1440 / (2 * Math.PI));
  return 86400 / Math.max(meanMotion, 0.1);
}

function propagateEcef(satrec, date, gmst) {
  const pv = satellite.propagate(satrec, date);
  if (!pv.position || !isFinite(pv.position.x)) return null;
  const geo = satellite.eciToGeodetic(pv.position, gmst);
  return {
    cartesian: Cesium.Cartesian3.fromDegrees(
      satellite.degreesLong(geo.longitude),
      satellite.degreesLat(geo.latitude),
      geo.height * 1000,
    ),
    lat: satellite.degreesLat(geo.latitude),
    lon: satellite.degreesLong(geo.longitude),
    altKm: geo.height,
  };
}

function punchColor(css) {
  const c = Cesium.Color.fromCssColorString(css);
  const max = Math.max(c.red, c.green, c.blue);
  const min = Math.min(c.red, c.green, c.blue);
  const l = (max + min) / 2;
  const d = max - min;
  let h = 0;
  let s = 0;
  if (d > 0.001) {
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (max === c.red) h = (c.green - c.blue) / d + (c.green < c.blue ? 6 : 0);
    else if (max === c.green) h = (c.blue - c.red) / d + 2;
    else h = (c.red - c.green) / d + 4;
    h /= 6;
  }
  return Cesium.Color.fromHsl(h, Math.min(1, s * 1.35 + 0.18), Math.min(0.62, Math.max(0.48, l)));
}

function baseAlpha(rec, selectedNorad) {
  if (selectedNorad && rec.norad !== selectedNorad) return 0.28;
  return 1;
}

function stylePoint(sat, selectedNorad) {
  const alpha = state.layers.sats ? baseAlpha(sat.rec, selectedNorad) : 0;
  const selected = sat.rec.norad === selectedNorad;
  sat.point.color = sat.color.withAlpha(alpha);
  sat.point.pixelSize = selected ? 14 : (sat.rec.coverage === "systematic" ? 11 : 8);
  sat.point.outlineColor = Cesium.Color.WHITE.withAlpha(alpha);
  sat.point.outlineWidth = selected ? 2 : 1;
}

function applyStyles() {
  const selected = state.selectedSatellite && state.selectedSatellite.norad;
  for (const sat of state.sats) stylePoint(sat, selected);
  if (points) points.show = state.layers.sats;
  if (orbitPrimitive) orbitPrimitive.show = state.layers.sats && Boolean(selected);
}

function bakeOrbit(sat, date) {
  const viewer = state.viewer;
  if (orbitPrimitive) {
    viewer.scene.primitives.remove(orbitPrimitive);
    orbitPrimitive = null;
  }
  const gmst = satellite.gstime(date);
  const period = periodSeconds(sat.satrec);
  const step = period / ORBIT_STEPS;
  const positions = [];
  const t0 = date.getTime();
  for (let i = 0; i <= ORBIT_STEPS; i++) {
    const t = new Date(t0 + i * step * 1000);
    const pose = propagateEcef(sat.satrec, t, gmst);
    if (pose) positions.push(pose.cartesian);
  }
  if (positions.length < 2) return;
  const color = sat.color;
  try {
    orbitPrimitive = new Cesium.Primitive({
      geometryInstances: new Cesium.GeometryInstance({
        geometry: new Cesium.PolylineGeometry({
          positions,
          width: 2,
          vertexFormat: Cesium.PolylineColorAppearance.VERTEX_FORMAT,
        }),
        attributes: {
          color: Cesium.ColorGeometryInstanceAttribute.fromColor(color.withAlpha(0.7)),
          depthFailColor: Cesium.ColorGeometryInstanceAttribute.fromColor(color.withAlpha(0.28)),
        },
      }),
      appearance: new Cesium.PolylineColorAppearance({ translucent: true }),
      depthFailAppearance: new Cesium.PolylineColorAppearance({ translucent: true }),
      asynchronous: false,
      allowPicking: false,
    });
  } catch {
    orbitPrimitive = null;
    return;
  }
  viewer.scene.primitives.add(orbitPrimitive);
  orbitGmst = gmst;
}

function rotateOrbit(date) {
  if (!orbitPrimitive) return;
  const delta = satellite.gstime(date) - orbitGmst;
  const rotation = Cesium.Matrix3.fromRotationZ(-delta, scratchRotation);
  orbitPrimitive.modelMatrix = Cesium.Matrix4.fromRotationTranslation(
    rotation,
    Cesium.Cartesian3.ZERO,
    scratchMatrix,
  );
}

function tick() {
  if (!window.satellite || !state.sats.length) return;
  const date = clockDate();
  const gmst = satellite.gstime(date);
  for (const sat of state.sats) {
    const pose = propagateEcef(sat.satrec, date, gmst);
    if (!pose) continue;
    sat.point.position = pose.cartesian;
    sat.lat = pose.lat;
    sat.lon = pose.lon;
    sat.altKm = pose.altKm;
  }
  rotateOrbit(date);
}

export function applyFleetFilter() {
  applyStyles();
}

export function selectSatellite(rec) {
  set({ selectedSatellite: rec, selectedDetection: null });
  const sat = state.sats.find((item) => item.rec.norad === rec.norad);
  if (!sat) return;
  bakeOrbit(sat, clockDate());
  applyStyles();
}

export function clearSatelliteSelection() {
  set({ selectedSatellite: null });
  if (orbitPrimitive && state.viewer) {
    state.viewer.scene.primitives.remove(orbitPrimitive);
    orbitPrimitive = null;
  }
  applyStyles();
  const cursor = $("hud-cursor");
  if (cursor) cursor.textContent = "—";
}

export async function loadSatellites() {
  const data = await getJSON("/api/satellites");
  const viewer = state.viewer;
  if (points) viewer.scene.primitives.remove(points);
  points = new Cesium.PointPrimitiveCollection();
  viewer.scene.primitives.add(points);
  const sats = [];
  for (const rec of data.satellites) {
    let satrec;
    try {
      satrec = satellite.twoline2satrec(rec.tle1, rec.tle2);
    } catch {
      continue;
    }
    const color = punchColor(rec.color);
    const systematic = rec.coverage === "systematic";
    const point = points.add({
      position: Cesium.Cartesian3.fromDegrees(0, 0, 700000),
      pixelSize: systematic ? 11 : 8,
      color,
      outlineColor: Cesium.Color.WHITE,
      outlineWidth: 1,
      scaleByDistance: new Cesium.NearFarScalar(1.2e6, 1.35, 2.4e7, 0.75),
      id: { satellite: rec },
    });
    sats.push({ rec, satrec, point, color });
    state.familiesOn[rec.family] = true;
  }
  set({ catalog: data, sats });
  if (!preRenderRemove) {
    preRenderRemove = viewer.scene.preRender.addEventListener(tick);
  }
  tick();
  return data;
}

export function satelliteForFamily(family) {
  const members = state.sats.filter((item) => item.rec.family === family && item.lat != null);
  if (!members.length) return null;
  const selected = state.selectedSatellite && state.selectedSatellite.norad;
  const idx = members.findIndex((item) => item.rec.norad === selected);
  if (idx >= 0 && members.length > 1) {
    return members[(idx + 1) % members.length].rec;
  }
  const camera = state.viewer && state.viewer.camera.positionWC;
  if (!camera) return members[0].rec;
  const camDir = Cesium.Cartesian3.normalize(camera, new Cesium.Cartesian3());
  const scratch = new Cesium.Cartesian3();
  let best = members[0];
  let bestDot = Infinity;
  for (const sat of members) {
    const pos = sat.point && sat.point.position;
    if (!pos) continue;
    const satDir = Cesium.Cartesian3.normalize(pos, scratch);
    const dot = Cesium.Cartesian3.dot(camDir, satDir);
    if (dot < bestDot) {
      bestDot = dot;
      best = sat;
    }
  }
  return best.rec;
}

const VIEW_ABOVE_M = 10_000_000;

export function flyToSelection() {
  const rec = state.selectedSatellite;
  const sat = rec && state.sats.find((item) => item.rec.norad === rec.norad);
  const pos = sat && sat.point && sat.point.position;
  if (!pos) return;
  state.viewer.trackedEntity = undefined;
  const radial = Cesium.Cartesian3.normalize(pos, new Cesium.Cartesian3());
  const destination = Cesium.Cartesian3.add(
    pos,
    Cesium.Cartesian3.multiplyByScalar(radial, VIEW_ABOVE_M, new Cesium.Cartesian3()),
    new Cesium.Cartesian3(),
  );
  state.viewer.camera.flyTo({
    destination,
    orientation: {
      heading: 0,
      pitch: Cesium.Math.toRadians(-90),
      roll: 0,
    },
    duration: 2.2,
    easingFunction: Cesium.EasingFunction.CUBIC_IN_OUT,
  });
}
