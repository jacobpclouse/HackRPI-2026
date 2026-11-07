import { getJSON } from "../api.js";
import { clockISO } from "../clock.js";
import { showScene } from "../globe/scene.js";
import { playNarration } from "../narration.js";
import { set, state } from "../state.js";
import { $ , esc } from "../ui/dom.js";
import { accessChip, km } from "../ui/format.js";

export function setTitle(text) {
  $("detail-title").textContent = text;
}

export function setBody(html) {
  $("detail-body").innerHTML = html;
}

function missionBlock(spec, deep) {
  if (!spec) return "<p class='empty'>No mission registry entry for this family.</p>";
  const chip = `<span class="chip ${spec.access}">${esc(accessChip(spec.access))}</span>`;
  const links = (spec.links || []).map((l) => `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)}</a>`).join("");
  const extra = (deep || []).map((l) => `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)}</a>`).join("");
  const verified = spec.verified_at ? `LINKS CHECKED ${spec.verified_at}` : "LINKS UNCHECKED";
  return (
    `<p>${chip} <span class="micro">${esc(spec.band)}-BAND · ${esc(spec.operator)}</span></p>` +
    `<p class="hint">${esc(spec.note || "")}</p>` +
    `<div class="links">${links}${extra}</div>` +
    `<p class="micro muted">${verified}</p>`
  );
}

export async function showSatellite(rec) {
  setTitle(`01 / ${rec.name}`);
  const spec = state.missions[rec.family];
  setBody("<p>Loading swath and mission registry.</p>");
  let deep = [];
  try {
    const sat = state.sats.find((item) => item.rec.norad === rec.norad);
    if (sat && sat.lat != null) {
      const miss = await getJSON(
        `/api/missions?family=${encodeURIComponent(rec.family)}&lat=${sat.lat}&lon=${sat.lon}&at=${encodeURIComponent(clockISO())}`,
      );
      deep = miss.deep_links || [];
    }
  } catch {
    /* registry still shown */
  }
  setBody(
    `<div class="kv"><span>Family</span><b>${esc(rec.family)}</b></div>` +
    `<div class="kv"><span>NORAD</span><b>${rec.norad}</b></div>` +
    `<div class="kv"><span>GP epoch</span><b>${esc(rec.epoch)}</b></div>` +
    `<div class="kv"><span>Look model</span><b>${esc(rec.look)}</b></div>` +
    `<div class="kv"><span>Coverage</span><b>${esc(rec.label)}</b></div>` +
    `<p class="hint">${esc(rec.note)}</p>` +
    missionBlock(spec, deep),
  );
}

export function renderPassDetail(data) {
  const longest = data.longest_gap;
  const rows = (data.passes || []).filter((p) => p.coverage === "systematic").slice(0, 12);
  const html = [
    longest ? `<p class="hero">${esc(longest.label.replace("no systematic swath for ", ""))}</p>` : "",
    longest ? `<p class="hint">${esc(longest.start.slice(5, 16).replace("T", " "))}Z → ${esc(longest.end.slice(5, 16).replace("T", " "))}Z. Computed from the pass list.</p>` : "",
    `<p><span class="chip on">SYSTEMATIC ${data.systematic_pass_count}</span><span class="chip">POSSIBLE ${data.possible_pass_count}</span></p>`,
    "<div class='list'>",
  ];
  for (const pass of rows) {
    html.push(
      `<div class="sat-card"><strong>${esc(pass.name)}</strong>` +
      `<small>${esc(pass.center.replace("T", " ").replace("Z", " Z"))} · cross-track ${pass.cross_km} km</small></div>`,
    );
  }
  html.push("</div>");
  setTitle("02 / COVERAGE");
  setBody(html.join(""));
}

export async function renderScenePanel() {
  setTitle("03 / SCENE");
  setBody("<p>Loading Sentinel-1 chip.</p>");
  try {
    const { scene, dets } = await showScene();
    const summary = scene.summary;
    const html = [
      `<p class="micro">${esc(summary.scene_id)}</p>`,
      `<div class="kv"><span>Acquisition</span><b>${esc(summary.scene_time)}</b></div>`,
      `<div class="kv"><span>Detections</span><b>${summary.detections}</b></div>`,
      `<div class="kv"><span>Matched</span><b>${summary.matched}</b></div>`,
      `<div class="kv"><span>Unmatched</span><b>${summary.unmatched}</b></div>`,
      `<p class="ethics">${esc(summary.note)}</p>`,
      `<div class="list" id="det-list"></div>`,
    ];
    setBody(html.join(""));
    const list = $("det-list");
    const rows = dets.features.slice().sort((a, b) => Number(a.properties.matched) - Number(b.properties.matched));
    for (const feature of rows) {
      const p = feature.properties;
      const card = document.createElement("div");
      card.className = "det-card" + (p.matched ? "" : " unmatched");
      const where = p.in_mpa ? `inside ${p.mpa_name || "MPA"}` : (p.near_mpa ? `within 5 km of ${p.mpa_name || "an MPA"}` : "not in a packaged MPA");
      card.innerHTML =
        `<strong>${esc(p.id)}</strong> ` +
        (p.matched
          ? `<span class="chip open">AIS ${esc(p.name || p.mmsi)}</span>`
          : `<span class="chip commercial">potential dark vessel</span>`) +
        `<small>${p.matched ? km(p.match_km) : "confidence " + esc(p.confidence)} · ${esc(p.peak_db)} dB · ${esc(p.shore_km)} km offshore · ${esc(where)}</small>`;
      card.addEventListener("click", () => focusDetection(feature));
      list.appendChild(card);
    }
  } catch (err) {
    setBody(`<p class="empty">${esc(err.message)}</p>`);
  }
}

async function focusDetection(feature) {
  const [lon, lat] = feature.geometry.coordinates;
  state.viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(lon, lat, 25000),
    duration: 2.5,
    easingFunction: Cesium.EasingFunction.CUBIC_IN_OUT,
  });
  set({ selectedDetection: feature });
  const props = feature.properties;
  if (props.matched) return;
  setTitle(`03 / ${props.id}`);
  setBody("<p>Loading brief.</p>");
  try {
    const brief = await getJSON("/api/briefs/" + encodeURIComponent(props.id));
    setBody(
      `<p>${esc(brief.text)}</p>` +
      `<p class="ethics">Unmatched means not matched to public AIS. It is not evidence of wrongdoing.</p>` +
      `<p class="hint">Brief source: ${esc(brief.provider)}${brief.error ? " (" + esc(brief.error) + ")" : ""}</p>` +
      `<p><button type="button" id="narrate-det">Play this brief</button></p>`,
    );
    $("narrate-det").addEventListener("click", () => playNarration("candidate", props.id));
  } catch (err) {
    setBody(`<p class="empty">${esc(err.message)}</p>`);
  }
}

export async function renderAnalysis() {
  setTitle("04 / ANALYSIS");
  setBody("<p>Computing scene-day passes and AIS silences.</p>");
  try {
    const story = await getJSON("/api/story");
    set({ story });
    const v = story.validation;
    const offset = v.nearest ? Math.abs(v.nearest.offset_s) : null;
    const offsetMin = offset == null
      ? "no predicted Sentinel-1 pass"
      : (offset < 90 ? offset.toFixed(0) + " s" : (offset / 60).toFixed(1) + " min");
    const longest = story.scene_day.longest_gap;
    const up = story.upcoming && story.upcoming.longest_gap;
    const b = story.intent_baseline || {};
    const expectedPct = b.expected_rate == null ? "—" : `${(b.expected_rate * 100).toFixed(1)}%`;
    const pText = b.p_value == null
      ? "No silences in the sample day."
      : (b.p_value > 0.05
        ? `p = ${b.p_value}. This sample does not show a pattern beyond chance.`
        : `p = ${b.p_value}. Onset clustering after passes is above the chance baseline.`);
    const silenceRows = (story.ais_silences || []).slice(0, 8).map((row) =>
      `<div class="sat-card"><strong>${esc(row.name)}</strong><small>MMSI ${esc(row.mmsi)} · no public AIS report for ${row.duration_h} h` +
      `${row.overlaps_coverage_gap ? " · " + (row.overlap_gap_s / 3600).toFixed(1) + " h of that sits in a SAR gap" : " · does not overlap a SAR gap"}</small></div>`,
    ).join("");
    setBody(
      `<p>Observed acquisition <strong class="data">${esc(story.observed_acquisition.time)}</strong>. Predicted Sentinel-1 offset: <strong class="data">${offsetMin}</strong> (${esc(v.quality)}).</p>` +
      (longest ? `<p class="hero">${esc(longest.label.replace("no systematic swath for ", ""))}</p>` : "") +
      (up ? `<p class="hint">Next 48 h from the GP epoch: ${esc(up.label)}.</p>` : "") +
      `<p>${story.ais_silence_count} tracks had no public AIS report for 30 minutes or more. ${story.silences_overlapping_gap} of those holes overlap a systematic coverage gap. Each swath pass is about a minute long, so a multi-hour reporting gap usually overlaps one. A missing report is not proof the transmitter was off.</p>` +
      `<p>Silences starting ≤${b.window_min || 30} min after a pass: <strong class="data">${b.observed_k} of ${b.n}</strong> (expected by chance: ${expectedPct}). ${pText}</p>` +
      `<div class="list">${silenceRows}</div>` +
      `<p class="hint">${esc(v.meaning)}</p>` +
      `<p class="ethics">${esc(story.ethics)}</p>`,
    );
    return story;
  } catch (err) {
    setBody(`<p class="empty">${esc(err.message)}</p>`);
    return null;
  }
}

export function idleInspector() {
  setTitle("01 / INSPECTOR");
  setBody(
    "<p>Satellites are propagated with satellite.js from CelesTrak GP elements. Click one for its mission registry entry and an approximate radar swath, offset from the ground track.</p>" +
    "<p class='ethics'>Unmatched means not matched to public AIS. It is not evidence of wrongdoing.</p>",
  );
}
