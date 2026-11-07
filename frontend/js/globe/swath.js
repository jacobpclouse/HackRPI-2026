import { getJSON } from "../api.js";
import { clockISO } from "../clock.js";
import { state } from "../state.js";
import { toast } from "../ui/dom.js";

let swathEntity = null;
let trackEntity = null;

export function clearSwath() {
  if (swathEntity) state.viewer.entities.remove(swathEntity);
  if (trackEntity) state.viewer.entities.remove(trackEntity);
  swathEntity = null;
  trackEntity = null;
}

export async function drawSwathFor(rec) {
  const feature = await getJSON(`/api/swath?norad=${rec.norad}&at=${encodeURIComponent(clockISO())}`);
  if (swathEntity) state.viewer.entities.remove(swathEntity);
  if (!feature.geometry) {
    toast(feature.properties && feature.properties.error, "/api/swath");
    return;
  }
  const ring = feature.geometry.coordinates[0];
  const flat = [];
  for (const pair of ring) flat.push(pair[0], pair[1]);
  const color = Cesium.Color.fromCssColorString(feature.properties.color || "#5ac8fa");
  const possible = feature.properties.coverage === "possible";
  swathEntity = state.viewer.entities.add({
    polygon: {
      hierarchy: Cesium.Cartesian3.fromDegreesArray(flat),
      material: possible
        ? new Cesium.StripeMaterialProperty({
            evenColor: color.withAlpha(0.18),
            oddColor: color.withAlpha(0.04),
            repeat: 18,
          })
        : color.withAlpha(0.1),
      outline: true,
      outlineColor: color,
      height: 0,
    },
    label: possible
      ? {
          text: "POSSIBLE",
          font: "11px JetBrains Mono, monospace",
          fillColor: Cesium.Color.fromCssColorString("#5ac8fa"),
          pixelOffset: new Cesium.Cartesian2(0, 18),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        }
      : undefined,
  });
  drawGroundTrack(rec);
}

function drawGroundTrack(rec) {
  if (trackEntity) state.viewer.entities.remove(trackEntity);
  const sat = state.sats.find((item) => item.rec.norad === rec.norad);
  if (!sat) return;
  const now = Cesium.JulianDate.toDate(state.viewer.clock.currentTime);
  const positions = [];
  for (let sec = -180; sec <= 360; sec += 20) {
    const date = new Date(now.getTime() + sec * 1000);
    const pv = satellite.propagate(sat.satrec, date);
    if (!pv.position) continue;
    const geo = satellite.eciToGeodetic(pv.position, satellite.gstime(date));
    positions.push(satellite.degreesLong(geo.longitude), satellite.degreesLat(geo.latitude));
  }
  trackEntity = state.viewer.entities.add({
    polyline: {
      positions: Cesium.Cartesian3.fromDegreesArray(positions),
      width: 1,
      material: Cesium.Color.fromCssColorString(rec.color).withAlpha(1),
      clampToGround: true,
    },
  });
}
