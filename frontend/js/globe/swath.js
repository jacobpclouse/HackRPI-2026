import { getJSON } from "../api.js";
import { clockISO } from "../clock.js";
import { state } from "../state.js";
import { toast } from "../ui/dom.js";

let swathEntity = null;

export function clearSwath() {
  if (swathEntity) state.viewer.entities.remove(swathEntity);
  swathEntity = null;
}

export async function drawSwathFor(rec) {
  const feature = await getJSON(`/api/swath?norad=${rec.norad}&at=${encodeURIComponent(clockISO())}`);
  if (swathEntity) state.viewer.entities.remove(swathEntity);
  swathEntity = null;
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
  });
}
