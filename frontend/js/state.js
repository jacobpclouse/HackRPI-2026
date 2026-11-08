/** Single store. Panels and globe modules talk through this, not each other's DOM. */

const listeners = new Set();

export const state = {
  mode: "orbit",
  selectedSatellite: null,
  selectedPoint: null,
  selectedDetection: null,
  region: null,
  familiesOn: {},
  layers: { sats: true, mpa: true, ais: true, det: true, possible: false },
  coverage: null,
  story: null,
  catalog: null,
  missions: {},
  health: null,
  model: null,
  viewer: null,
  sats: [],
  sceneOn: false,
  basemap: "imagery",
  clockLive: true,
  clockSpeed: 1,
  clockOffsetMs: 0,
  clockPaused: false,
  // Reserved for later features. Do not remove.
  catchCone: null,
  rendezvous: null,
  spoofed: null,
};

export function get() {
  return state;
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function set(patch) {
  Object.assign(state, patch);
  for (const fn of listeners) fn(state, patch);
}
