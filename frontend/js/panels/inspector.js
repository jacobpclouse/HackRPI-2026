import { set, state } from "../state.js";
import { $, esc } from "../ui/dom.js";
import { accessChip, km } from "../ui/format.js";

export function setTitle(text) {
  $("card-title").textContent = text;
}

export function setBody(html) {
  $("card-body").innerHTML = html;
}

export function hideCard() {
  $("card").hidden = true;
  set({ selectedDetection: null });
}

function showCard() {
  $("card").hidden = false;
}

export function showSatellite(rec) {
  const spec = state.missions[rec.family];
  const access = spec ? `<span class="chip ${esc(spec.access)}">${esc(accessChip(spec.access))}</span>` : "";
  setTitle(rec.name);
  setBody(
    `<div class="kv"><span>Family</span><b>${esc(rec.family)}</b></div>` +
    `<div class="kv"><span>NORAD</span><b>${rec.norad}</b></div>` +
    (spec ? `<p>${access} <span class="micro">${esc(spec.band)}-BAND</span></p>` : "") +
    `<p class="hint">${esc(rec.note || rec.label || "")}</p>`,
  );
  showCard();
}

export function showDetection(feature) {
  const p = feature.properties;
  set({ selectedDetection: feature });
  setTitle(p.id);
  if (p.matched) {
    setBody(
      `<p><span class="chip open">AIS ${esc(p.name || p.mmsi)}</span></p>` +
      `<p class="hint">${km(p.match_km)} from public AIS.</p>`,
    );
  } else {
    const where = p.in_mpa
      ? `inside ${p.mpa_name || "an MPA"}`
      : (p.near_mpa ? `near ${p.mpa_name || "an MPA"}` : `${esc(p.shore_km)} km offshore`);
    setBody(
      `<p><span class="chip commercial">not on public AIS</span></p>` +
      `<div class="kv"><span>Peak</span><b>${Number(p.peak_db).toFixed(1)} dB</b></div>` +
      `<div class="kv"><span>Where</span><b>${esc(where)}</b></div>` +
      `<p class="ethics">Unmatched means not matched to public AIS. It is not evidence of wrongdoing.</p>`,
    );
  }
  showCard();
}

export function focusDetection(feature) {
  const [lon, lat] = feature.geometry.coordinates;
  state.viewer.trackedEntity = undefined;
  state.viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(lon, lat, 25000),
    duration: 2.5,
    easingFunction: Cesium.EasingFunction.CUBIC_IN_OUT,
  });
  showDetection(feature);
}

export function idleInspector() {
  hideCard();
}
