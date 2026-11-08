import { state } from "../state.js";
import { setCopernicusCovering } from "./scene.js";

let layer = null;
let moveListener = null;
let moveTimer = 0;
let requestSeq = 0;
let paintedKey = "";
let current = null;
let hooks = null;
const appearance = { brightness: 1, contrast: 1, gamma: 1.2, alpha: 1 };

function apply(target = layer) {
  if (!target) return;
  target.brightness = appearance.brightness;
  target.contrast = appearance.contrast;
  target.gamma = appearance.gamma;
  target.alpha = appearance.alpha;
}

export function setAppearance(next) {
  Object.assign(appearance, next);
  apply();
}

function overlap(view, bbox) {
  const west = Math.max(view.west, bbox[0]);
  const south = Math.max(view.south, bbox[1]);
  const east = Math.min(view.east, bbox[2]);
  const north = Math.min(view.north, bbox[3]);
  if (east - west < 0.02 || north - south < 0.02) return null;
  const step = 0.01;
  return {
    west: Math.floor(west / step) * step,
    south: Math.floor(south / step) * step,
    east: Math.ceil(east / step) * step,
    north: Math.ceil(north / step) * step,
  };
}

function viewBox() {
  const rect = state.viewer.camera.computeViewRectangle(Cesium.Ellipsoid.WGS84);
  if (!rect) return null;
  const west = Cesium.Math.toDegrees(rect.west);
  const south = Cesium.Math.toDegrees(rect.south);
  const east = Cesium.Math.toDegrees(rect.east);
  const north = Cesium.Math.toDegrees(rect.north);
  if (!(east > west) || east - west > 12 || north - south > 12) return null;
  return { west, south: Math.max(-85, south), east, north: Math.min(85, north) };
}

export function hideImagery() {
  window.clearTimeout(moveTimer);
  requestSeq += 1;
  current = null;
  hooks = null;
  paintedKey = "";
  if (moveListener && state.viewer) {
    state.viewer.camera.moveEnd.removeEventListener(moveListener);
  }
  moveListener = null;
  if (layer && state.viewer) {
    state.viewer.imageryLayers.remove(layer, true);
  }
  layer = null;
  setCopernicusCovering(false);
}

async function paintView() {
  if (!current || !state.viewer) return;
  const seq = ++requestSeq;
  const view = viewBox();
  const box = view && overlap(view, current.acquisition.bbox);
  if (!box) {
    if (hooks) hooks.onMiss();
    return;
  }
  const key = [
    current.acquisition.id,
    current.viz,
    box.west.toFixed(2),
    box.south.toFixed(2),
    box.east.toFixed(2),
    box.north.toFixed(2),
  ].join("|");
  if (key === paintedKey && layer) {
    if (hooks) hooks.onReady();
    return;
  }
  if (hooks) hooks.onLoading();
  const params = new URLSearchParams({
    start: current.acquisition.start,
    end: current.acquisition.end,
    polarization: current.acquisition.polarization,
    viz: current.viz,
    west: String(box.west),
    south: String(box.south),
    east: String(box.east),
    north: String(box.north),
    orbit: (current.acquisition.orbit || "").toUpperCase(),
    footprint_west: String(current.acquisition.bbox[0]),
    footprint_south: String(current.acquisition.bbox[1]),
    footprint_east: String(current.acquisition.bbox[2]),
    footprint_north: String(current.acquisition.bbox[3]),
  });
  try {
    const provider = await Cesium.SingleTileImageryProvider.fromUrl(`/api/copernicus/view.png?${params}`, {
      rectangle: Cesium.Rectangle.fromDegrees(box.west, box.south, box.east, box.north),
    });
    if (seq !== requestSeq || !current) return;
    const next = state.viewer.imageryLayers.addImageryProvider(provider);
    apply(next);
    if (layer) state.viewer.imageryLayers.remove(layer, true);
    layer = next;
    paintedKey = key;
    setCopernicusCovering(true);
    if (hooks) hooks.onReady();
  } catch {
    if (seq !== requestSeq) return;
    if (hooks) hooks.onError();
  }
}

export function showAcquisition(acquisition, viz, nextHooks) {
  const samePass = current && current.acquisition.id === acquisition.id && current.viz === viz;
  current = { acquisition, viz };
  hooks = nextHooks || hooks;
  if (!samePass) {
    paintedKey = "";
    if (layer && state.viewer) {
      state.viewer.imageryLayers.remove(layer, true);
      layer = null;
      setCopernicusCovering(false);
    }
  }
  if (!moveListener && state.viewer) {
    moveListener = () => {
      window.clearTimeout(moveTimer);
      moveTimer = window.setTimeout(paintView, 600);
    };
    state.viewer.camera.moveEnd.addEventListener(moveListener);
  }
  paintView();
}

export function imageryVisible() {
  return layer != null;
}
