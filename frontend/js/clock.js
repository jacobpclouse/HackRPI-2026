import { set } from "./state.js";
import { $ } from "./ui/dom.js";
import { offsetLabel, utcStamp } from "./ui/format.js";

const SPEEDS = [1, 10, 60, 300];
let viewer = null;
let speedBeforeScrub = 1;
let scrubbing = false;

export function bindClock(v) {
  viewer = v;
  viewer.clock.shouldAnimate = true;
  viewer.clock.multiplier = 1;
  viewer.clock.currentTime = Cesium.JulianDate.now();
}

export function clockDate() {
  return Cesium.JulianDate.toDate(viewer.clock.currentTime);
}

export function clockISO() {
  return clockDate().toISOString();
}

export function coverageStart() {
  const start = clockDate();
  start.setUTCSeconds(0, 0);
  start.setUTCMinutes(start.getUTCMinutes() - (start.getUTCMinutes() % 10));
  return start;
}

export function isLive() {
  const offset = clockDate().getTime() - Date.now();
  return viewer.clock.multiplier === 1 && Math.abs(offset) <= 5000 && viewer.clock.shouldAnimate;
}

export function returnToLive() {
  viewer.clock.currentTime = Cesium.JulianDate.now();
  viewer.clock.multiplier = 1;
  viewer.clock.shouldAnimate = true;
  publish();
}

export function cycleSpeed() {
  const i = SPEEDS.indexOf(viewer.clock.multiplier);
  viewer.clock.multiplier = SPEEDS[(i + 1) % SPEEDS.length];
  viewer.clock.shouldAnimate = true;
  publish();
}

export function togglePause() {
  viewer.clock.shouldAnimate = !viewer.clock.shouldAnimate;
  publish();
}

export function setTime(date) {
  viewer.clock.currentTime = Cesium.JulianDate.fromDate(date);
  publish();
}

export function beginScrub() {
  speedBeforeScrub = viewer.clock.multiplier || 1;
  viewer.clock.shouldAnimate = false;
  scrubbing = true;
}

export function endScrub() {
  viewer.clock.multiplier = speedBeforeScrub;
  viewer.clock.shouldAnimate = true;
  scrubbing = false;
  publish();
}

export function publish() {
  if (!scrubbing && viewer.clock.multiplier === 1 && viewer.clock.shouldAnimate) {
    viewer.clock.currentTime = Cesium.JulianDate.now();
  }
  const now = clockDate();
  const offset = now.getTime() - Date.now();
  const live = isLive();
  set({
    clockLive: live,
    clockSpeed: viewer.clock.multiplier,
    clockOffsetMs: offset,
    clockPaused: !viewer.clock.shouldAnimate,
  });
  $("utc").textContent = utcStamp(now);
  const badge = $("badge");
  badge.textContent = live ? "LIVE" : "SIM";
  badge.className = "badge " + (live ? "live" : "sim");
  const off = $("offset");
  off.hidden = live;
  off.textContent = live ? "" : offsetLabel(offset);
  $("speed").textContent = viewer.clock.multiplier + "\u00d7";
  $("live").hidden = live;
}

export function onTick(fn) {
  viewer.clock.onTick.addEventListener(() => {
    publish();
    fn(clockDate());
  });
}
