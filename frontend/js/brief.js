import { getJSON } from "./api.js";
import { esc } from "./ui/dom.js";

const root = document.getElementById("brief");

function render(data) {
  const scene = data.scene || {};
  const nar = data.narrative || {};
  const prov = data.provenance || {};
  const date = (scene.datetime || "").slice(0, 10);
  document.title = `Nimbus incident brief · Kattegat`;
  const rows = (data.candidates || []).map((facts) => {
    const tgt = facts.target || {};
    const pri = facts.priority || {};
    const ais = facts.ais_context || {};
    const pers = facts.persistence || {};
    const jur = facts.jurisdiction || {};
    const best = facts.best_next || {};
    const fp = tgt.footprint || {};
    return `<tr>` +
      `<td><a href="/case.html?id=${esc(facts.case.id)}">${esc(facts.case.id)}</a></td>` +
      `<td><span class="badge pri ${esc(pri.tier || "")}">${esc(pri.tier || "")}</span></td>` +
      `<td>${esc(tgt.position_ddm || "")}</td>` +
      `<td>${esc((fp.length_m_range || "—"))}</td>` +
      `<td>${ais.within_5km ? "yes" : "no"}</td>` +
      `<td>${esc((pers && pers.verdict) || "—")}</td>` +
      `<td>${esc(jur.nearest_coast_country || "—")} · 12 nm ${jur.likely_territorial_sea ? "yes" : "no"}</td>` +
      `<td>${esc(best.start || "—")}</td>` +
      `</tr>`;
  }).join("");
  root.innerHTML =
    `<header class="band"><div>` +
    `<h1>Nimbus incident brief · Kattegat · ${esc(date)}</h1>` +
    `<p class="marking">${esc(data.marking || "")}</p>` +
    `</div><p class="scene-id">${esc(data.generated_at || "")}</p></header>` +
    `<p class="bluf">${esc(nar.summary || "")}</p>` +
    `<p class="provenance">${esc(prov.line || "")}</p>` +
    `<div class="map-wrap"><img alt="Incident map" src="/api/brief/map.svg" /></div>` +
    `<table class="plan-table"><thead><tr>` +
    `<th>ID</th><th>Priority</th><th>LKP</th><th>Length</th><th>AIS ≤5 km</th><th>Persistence</th><th>Jurisdiction</th><th>Best next</th>` +
    `</tr></thead><tbody>${rows}</tbody></table>` +
    `<p class="disclaimer">${esc(data.limits || "")}</p>` +
    `<p class="method-note">Approximate: nearest coastline and 12 nm distance. Official maritime boundaries were not computed.</p>`;
}

async function main() {
  document.getElementById("brief-print").addEventListener("click", () => window.print());
  try {
    render(await getJSON("/api/brief"));
  } catch (err) {
    root.innerHTML = `<p>${esc(err.message || "Incident brief unavailable.")}</p>`;
  }
}

main();
