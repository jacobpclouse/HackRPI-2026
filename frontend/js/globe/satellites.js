import { getJSON } from "../api.js";
import { set, state } from "../state.js";
import { $ } from "../ui/dom.js";

function diamond(color) {
  const c = document.createElement("canvas");
  c.width = 12;
  c.height = 12;
  const g = c.getContext("2d");
  g.fillStyle = color;
  g.beginPath();
  g.moveTo(6, 1);
  g.lineTo(11, 6);
  g.lineTo(6, 11);
  g.lineTo(1, 6);
  g.closePath();
  g.fill();
  return c;
}

function reticleCanvas() {
  const c = document.createElement("canvas");
  c.width = 48;
  c.height = 48;
  const g = c.getContext("2d");
  g.strokeStyle = "#e6eaf0";
  g.lineWidth = 1.25;
  const draw = (x, y, dx, dy) => {
    g.beginPath();
    g.moveTo(x, y + dy);
    g.lineTo(x, y);
    g.lineTo(x + dx, y);
    g.stroke();
  };
  draw(4, 4, 10, 10);
  draw(44, 4, -10, 10);
  draw(4, 44, 10, -10);
  draw(44, 44, -10, -10);
  return c;
}

let reticle = null;

export function applyFleetFilter() {
  for (const sat of state.sats) {
    sat.entity.show = state.layers.sats && state.familiesOn[sat.rec.family] !== false;
  }
}

export function updateSatellites(date) {
  if (!window.satellite) return;
  const gmst = satellite.gstime(date);
  for (const sat of state.sats) {
    if (!sat.entity.show) continue;
    const pv = satellite.propagate(sat.satrec, date);
    if (!pv.position || !isFinite(pv.position.x)) continue;
    const geo = satellite.eciToGeodetic(pv.position, gmst);
    const lat = satellite.degreesLat(geo.latitude);
    const lon = satellite.degreesLong(geo.longitude);
    sat.entity.position = Cesium.Cartesian3.fromDegrees(lon, lat, geo.height * 1000);
    sat.lat = lat;
    sat.lon = lon;
    sat.altKm = geo.height;
  }
  const sel = state.selectedSatellite;
  if (reticle && sel) {
    const sat = state.sats.find((item) => item.rec.norad === sel.norad);
    if (sat) reticle.position = sat.entity.position;
  }
}

export function selectSatellite(rec) {
  set({ selectedSatellite: rec });
  if (reticle) state.viewer.entities.remove(reticle);
  const sat = state.sats.find((item) => item.rec.norad === rec.norad);
  if (!sat) return;
  reticle = state.viewer.entities.add({
    position: sat.entity.position,
    billboard: {
      image: reticleCanvas(),
      width: 36,
      height: 36,
      disableDepthTestDistance: Number.POSITIVE_INFINITY,
    },
  });
}

export function clearSatelliteSelection() {
  set({ selectedSatellite: null });
  if (reticle) {
    state.viewer.entities.remove(reticle);
    reticle = null;
  }
}

export async function loadSatellites() {
  const data = await getJSON("/api/satellites");
  const viewer = state.viewer;
  const families = {};
  const sats = [];
  for (const rec of data.satellites) {
    let satrec;
    try {
      satrec = satellite.twoline2satrec(rec.tle1, rec.tle2);
    } catch {
      continue;
    }
    const systematic = rec.coverage === "systematic";
    const entity = viewer.entities.add({
      name: rec.name,
      position: Cesium.Cartesian3.fromDegrees(0, 0, 700000),
      billboard: systematic
        ? {
            image: diamond(rec.color),
            width: 10,
            height: 10,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          }
        : undefined,
      point: systematic
        ? undefined
        : {
            pixelSize: 3,
            color: Cesium.Color.fromCssColorString(rec.color).withAlpha(0.5),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
      label: {
        text: systematic ? rec.name : "",
        font: "11px JetBrains Mono, monospace",
        fillColor: Cesium.Color.fromCssColorString("#e6eaf0"),
        show: systematic,
        pixelOffset: new Cesium.Cartesian2(10, -8),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        scaleByDistance: new Cesium.NearFarScalar(8e5, 1, 2e7, 0.3),
      },
    });
    entity.satellite = rec;
    sats.push({ rec, satrec, entity });
    families[rec.family] = families[rec.family] || { count: 0, coverage: rec.coverage, color: rec.color };
    families[rec.family].count += 1;
    state.familiesOn[rec.family] = true;
  }
  set({ catalog: data, sats });
  const skipped = (data.skipped || []).filter((row) => row.reason && !/not a SAR mission/.test(row.reason));
  $("catalog-status").textContent =
    `${data.count} SAR objects · CelesTrak ${data.origin || ""} ${data.fetched_at || ""}`.trim();
  const box = $("families");
  box.innerHTML = "";
  Object.keys(families).sort().forEach((name) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip on";
    btn.textContent = `${name} ${families[name].count}`;
    btn.addEventListener("click", () => {
      state.familiesOn[name] = !state.familiesOn[name];
      btn.classList.toggle("on", state.familiesOn[name]);
      applyFleetFilter();
    });
    box.appendChild(btn);
  });
  if (skipped.length) {
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = skipped.slice(0, 4).map((row) => `${row.name || "query"}: ${row.reason}`).join(" ");
    box.after(note);
  }
  return data;
}

export function flyToSelection() {
  const rec = state.selectedSatellite;
  const sat = rec && state.sats.find((item) => item.rec.norad === rec.norad);
  if (!sat || sat.lon == null) return;
  state.viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(sat.lon, sat.lat, Math.max(400000, (sat.altKm || 700) * 400)),
    duration: 2.5,
    easingFunction: Cesium.EasingFunction.CUBIC_IN_OUT,
  });
}
