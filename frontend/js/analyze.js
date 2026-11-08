import { getJSON } from "./api.js";
import { showUploadDetections } from "./globe/scene.js";
import { setExtraExclude } from "./globe/ships.js";
import { set, state } from "./state.js";
import { $, esc } from "./ui/dom.js";

const ACCENT = "#e6eaf0";
const MATCHED = "#3dd68c";
const DARK = "#ff4d4f";
const GAP = "#f5a524";
const MUTED = "#545e6c";

let result = null;
let lookImg = null;
let annImg = null;
let cam = { x: 0, y: 0, scale: 1 };
let sortKey = "score";
let selected = null;
let compare = false;
let slider = 0.5;
let drag = null;
let splitDrag = false;
let selectedSample = null;

function page() { return $("analyze"); }

export function openAnalyze() {
  page().hidden = false;
  set({ analyzeOn: true });
  if (location.hash !== "#analyze") location.hash = "analyze";
  loadSamples();
}

export function closeAnalyze() {
  page().hidden = true;
  set({ analyzeOn: false });
  if (location.hash === "#analyze") history.replaceState(null, "", location.pathname + location.search);
}

export function isAnalyzeOpen() {
  return !page().hidden;
}

async function loadSamples() {
  try {
    const data = await getJSON("/api/imagery/samples");
    $("analyze-samples").innerHTML = (data.samples || []).map((s) => (
      `<button type="button" data-sample="${esc(s.name)}" class="${selectedSample === s.name ? "on" : ""}">${esc(s.title)}<br><span class="micro">${esc(s.description)}</span></button>`
    )).join("");
  } catch {
    $("analyze-samples").innerHTML = `<p class="hint">Samples unavailable.</p>`;
  }
}

function resetViewer() {
  cam = { x: 0, y: 0, scale: 1 };
}

function boxColor(det) {
  const ais = det.ais && det.ais.status;
  if (ais === "matched") return MATCHED;
  if (ais === "dark_candidate") return DARK;
  if (det.status === "vessel_like") return ACCENT;
  return MUTED;
}

function draw() {
  const canvas = $("analyze-canvas");
  if (!canvas || !lookImg) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width = canvas.clientWidth;
  const h = canvas.height = canvas.clientHeight;
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, w, h);
  const img = (compare && annImg) ? annImg : lookImg;
  const iw = lookImg.naturalWidth;
  const ih = lookImg.naturalHeight;
  const fit = Math.min(w / iw, h / ih);
  const s = fit * cam.scale;
  const x = (w - iw * s) / 2 + cam.x;
  const y = (h - ih * s) / 2 + cam.y;
  canvas._map = { x, y, s, scale: result ? result.quicklook_scale || 1 : 1 };
  if (compare && annImg) {
    const split = w * slider;
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, split, h);
    ctx.clip();
    ctx.drawImage(lookImg, x, y, iw * s, ih * s);
    ctx.restore();
    ctx.save();
    ctx.beginPath();
    ctx.rect(split, 0, w - split, h);
    ctx.clip();
    ctx.drawImage(annImg, x, y, iw * s, ih * s);
    ctx.restore();
    ctx.fillStyle = ACCENT;
    ctx.fillRect(split - 1, 0, 2, h);
  } else {
    ctx.drawImage(img, x, y, iw * s, ih * s);
    drawBoxes(ctx, canvas._map);
  }
  drawScale(iw, s);
}

function drawBoxes(ctx, map) {
  if (!result) return;
  const showRej = $("analyze-show-rejected").checked;
  const showGt = $("analyze-show-labels").checked;
  const sc = map.scale;
  for (const det of result.detections || []) {
    if (det.status === "edge") continue;
    if (det.status === "rejected" && !showRej) continue;
    const [x0, y0, x1, y1] = det.bbox;
    const k = map.s / sc;
    const a = map.x + x0 * k;
    const b = map.y + y0 * k;
    const c = map.x + x1 * k;
    const d = map.y + y1 * k;
    ctx.strokeStyle = boxColor(det);
    ctx.lineWidth = det.status === "rejected" ? 1 : 1.5;
    if (det.status === "rejected") ctx.setLineDash([4, 3]);
    else ctx.setLineDash([]);
    ctx.strokeRect(a, b, c - a, d - b);
    if (det.status === "vessel_like") {
      const L = 6;
      ctx.beginPath();
      ctx.moveTo(a, b + L); ctx.lineTo(a, b); ctx.lineTo(a + L, b);
      ctx.moveTo(c, b + L); ctx.lineTo(c, b); ctx.lineTo(c - L, b);
      ctx.moveTo(a, d - L); ctx.lineTo(a, d); ctx.lineTo(a + L, d);
      ctx.moveTo(c, d - L); ctx.lineTo(c, d); ctx.lineTo(c - L, d);
      ctx.stroke();
    }
    if (det.ais && det.ais.status === "dark_candidate") {
      ctx.fillStyle = DARK;
      ctx.font = "10px JetBrains Mono, monospace";
      ctx.fillText(det.id, a, b - 2);
    }
    if (selected && selected.id === det.id) {
      ctx.strokeStyle = ACCENT;
      ctx.setLineDash([]);
      ctx.strokeRect(a - 2, b - 2, c - a + 4, d - b + 4);
    }
  }
  const gt = result.ground_truth;
  if (showGt && gt && gt.boxes) {
    ctx.setLineDash([6, 4]);
    ctx.strokeStyle = DARK;
    ctx.lineWidth = 2;
    const k = map.s / sc;
    for (const box of gt.boxes) {
      const [x0, y0, x1, y1] = box.bbox;
      const a = map.x + x0 * k;
      const b = map.y + y0 * k;
      ctx.strokeRect(a, b, (x1 - x0) * k, (y1 - y0) * k);
    }
  }
  ctx.setLineDash([]);
}

function drawScale(iw, s) {
  const el = $("analyze-scale");
  if (!result || result.spacing_m == null) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  const meters = result.spacing_m * (80 / (s / ((result.quicklook_scale || 1))));
  // 80 px on screen ≈
  const span = (80 / s) * (result.spacing_m / (result.quicklook_scale || 1));
  el.textContent = `${span >= 1000 ? (span / 1000).toFixed(1) + " km" : Math.round(span) + " m"}`;
}

function hitTest(mx, my) {
  const canvas = $("analyze-canvas");
  const map = canvas._map;
  if (!map || !result) return null;
  const k = map.s / (result.quicklook_scale || 1);
  const showRej = $("analyze-show-rejected").checked;
  for (const det of (result.detections || []).slice().reverse()) {
    if (det.status === "edge") continue;
    if (det.status === "rejected" && !showRej) continue;
    const [x0, y0, x1, y1] = det.bbox;
    const a = map.x + x0 * k;
    const b = map.y + y0 * k;
    const c = map.x + x1 * k;
    const d = map.y + y1 * k;
    if (mx >= a && mx <= c && my >= b && my <= d) return det;
  }
  return null;
}

function countUp(el, value, suffix) {
  const end = Number(value) || 0;
  const t0 = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - t0) / 400);
    const v = end * (1 - (1 - t) ** 2);
    el.textContent = (Number.isInteger(end) ? Math.round(v) : v.toFixed(2)) + (suffix || "");
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function renderHeroes() {
  const h = result.heroes || {};
  const extra = [];
  if (result.area_km2 != null) extra.push(["AREA ANALYZED", `${result.area_km2} km²`]);
  if (result.spacing_m != null) extra.push(["PIXEL SPACING", `${result.spacing_m} m ${result.spacing_label || ""}`]);
  $("analyze-heroes").innerHTML = [
    ["SHIPS FOUND", h.ships_found, ""],
    ["REJECTED", h.rejected, ""],
    ["MEAN CONFIDENCE", h.mean_confidence, ""],
    ["PROCESSED IN", h.processed_s, " s"],
  ].map(([label, value, suf]) => (
    `<div><span class="micro">${label}</span><p class="hero" data-v="${value ?? "—"}" data-s="${suf}">${value ?? "—"}</p></div>`
  )).join("") + extra.map(([l, v]) => `<div><span class="micro">${l}</span><p>${esc(v)}</p></div>`).join("");
  $("analyze-heroes").querySelectorAll(".hero").forEach((el) => {
    if (el.dataset.v !== "—" && el.dataset.v !== "null") countUp(el, el.dataset.v, el.dataset.s);
  });
  const gt = result.ground_truth;
  if (gt && gt.available) {
    $("analyze-gt").innerHTML =
      `<div class="kv"><span>RECALL</span><b>${gt.tp} of ${gt.n_gt}</b></div>` +
      `<div class="kv"><span>PRECISION</span><b>${(gt.precision * 100).toFixed(0)}%</b></div>`;
  } else $("analyze-gt").innerHTML = "";
  const ais = result.ais;
  if (ais && ais.available) {
    const src = result.acquisition ? `${result.acquisition.time} (${result.acquisition.source.replace("_", " ")})` : "";
    $("analyze-ais").innerHTML =
      `<div class="kv"><span>AIS MATCHED</span><b>${ais.matched}</b></div>` +
      `<div class="kv"><span>DARK CANDIDATES</span><b>${ais.dark_candidates}</b></div>` +
      `<div class="kv"><span>AIS-ONLY</span><b>${(ais.ais_only || []).length}</b></div>` +
      `<p class="hint">${esc(src)}</p>`;
  } else $("analyze-ais").innerHTML = ais && ais.reason ? `<p class="hint">${esc(ais.reason)}</p>` : "";
}

function renderFunnel() {
  const f = result.funnel || {};
  const stages = [
    ["INGEST", "1", f.ingest && f.ingest.ms],
    ["NORMALIZE", "1", f.normalize && f.normalize.ms],
    ["PROPOSE", String((f.propose && f.propose.count) ?? "—"), f.propose && f.propose.ms],
    ["CLASSIFY", f.classify ? `${f.classify.keep} / ${f.classify.reject}` : "—", f.classify && f.classify.ms],
    ["AIS", f.ais ? `${f.ais.matched} / ${f.ais.dark}` : "—", f.ais && f.ais.ms],
  ];
  $("analyze-funnel").innerHTML = stages.map(([n, c, ms]) => (
    `<div class="funnel-stage"><strong>${n}</strong><div>${esc(c)}</div><span class="micro">${ms != null ? ms + " ms" : ""}</span></div>`
  )).join("");
  [...$("analyze-funnel").children].forEach((el, i) => {
    setTimeout(() => el.classList.add("on"), 120 * i);
  });
}

function renderHist() {
  const canvas = $("analyze-hist");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const hist = result.histogram;
  if (!hist) return;
  const max = Math.max(1, ...hist.counts);
  const bw = canvas.width / hist.counts.length;
  ctx.fillStyle = MUTED;
  hist.counts.forEach((n, i) => {
    const h = (n / max) * (canvas.height - 16);
    ctx.fillRect(i * bw + 1, canvas.height - 14 - h, bw - 2, h);
  });
  const tx = hist.threshold * canvas.width;
  ctx.strokeStyle = GAP;
  ctx.beginPath();
  ctx.moveTo(tx, 0);
  ctx.lineTo(tx, canvas.height - 14);
  ctx.stroke();
  ctx.fillStyle = GAP;
  ctx.font = "10px JetBrains Mono, monospace";
  ctx.fillText(hist.threshold.toFixed(3), Math.min(canvas.width - 40, tx + 4), 10);
}

function renderTable() {
  const rows = (result.detections || []).filter((d) => d.status !== "edge");
  rows.sort((a, b) => {
    if (sortKey === "length") return (b.length_m || 0) - (a.length_m || 0);
    if (sortKey === "status") return a.status.localeCompare(b.status);
    return (b.score || 0) - (a.score || 0);
  });
  $("analyze-table").innerHTML =
    `<thead><tr><th></th><th data-k="id">ID</th><th data-k="score">SCORE</th><th data-k="status">STATUS</th><th data-k="length">LENGTH</th><th>LAT / LON</th><th>AIS</th></tr></thead><tbody>` +
    rows.map((d) => {
      const pct = d.score == null ? 0 : d.score * 100;
      const ais = d.ais ? (d.ais.status === "matched" ? esc(d.ais.name || d.ais.mmsi) : d.ais.status) : "—";
      const ll = d.lat != null ? `${Number(d.lat).toFixed(4)}, ${Number(d.lon).toFixed(4)}` : "—";
      return `<tr data-id="${d.id}" class="${selected && selected.id === d.id ? "on" : ""}">` +
        `<td>${d.chip_url ? `<img src="${esc(d.chip_url)}" width="32" height="32" alt="" />` : ""}</td>` +
        `<td>${esc(d.id)}</td>` +
        `<td><div class="score-bar"><div class="score-fill" style="width:${pct}%"></div><span class="score-tick" style="left:${(result.threshold * 100).toFixed(1)}%"></span></div></td>` +
        `<td>${esc(d.status)}</td>` +
        `<td>${d.length_m} m</td>` +
        `<td>${ll}</td>` +
        `<td>${ais}</td></tr>`;
    }).join("") + `</tbody>`;
}

function selectDet(det) {
  selected = det;
  if (det && det.chip_url) {
    $("analyze-chip-zoom").innerHTML = `<img src="${esc(det.chip_url)}" alt="${esc(det.id)}" />`;
  }
  renderTable();
  draw();
}

async function loadImages(data) {
  lookImg = new Image();
  annImg = new Image();
  await Promise.all([
    new Promise((res) => { lookImg.onload = res; lookImg.src = data.quicklook_url; }),
    new Promise((res) => { annImg.onload = res; annImg.src = data.annotated_url; }),
  ]);
  resetViewer();
  draw();
}

function applyResult(data) {
  result = data;
  set({ analysis: data });
  $("analyze-mode").textContent = data.mode_note || "";
  $("analyze-footnote").textContent = data.footnote || "";
  $("analyze-dl-png").hidden = false;
  $("analyze-dl-png").href = data.annotated_url;
  $("analyze-dl-png").download = "annotated.png";
  $("analyze-dl-json").hidden = false;
  $("analyze-dl-json").href = data.report_url;
  $("analyze-dl-json").download = "report.json";
  $("analyze-globe").hidden = !(data.kind === "geotiff" && data.bbox);
  $("analyze-model").textContent = data.threshold != null
    ? `Threshold ${Number(data.threshold).toFixed(3)}. 64×64 VV chips.`
    : "";
  renderHeroes();
  renderFunnel();
  renderHist();
  renderTable();
  loadImages(data);
}

async function postAnalyze(url, body) {
  $("analyze-funnel").innerHTML = ["INGEST", "NORMALIZE", "PROPOSE", "CLASSIFY", "AIS"].map((n) => (
    `<div class="funnel-stage"><strong>${n}</strong></div>`
  )).join("");
  const response = await fetch(url, { method: "POST", body });
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).error || detail; } catch { /* keep */ }
    $("analyze-heroes").innerHTML = `<p>${esc(detail)}</p>`;
    return;
  }
  applyResult(await response.json());
}

export function wireAnalyze({ onShowGlobe }) {
  $("analyze-open").addEventListener("click", openAnalyze);
  $("analyze-close").addEventListener("click", closeAnalyze);
  $("analyze-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const image = $("analyze-image").files[0];
    if (!image) return;
    const body = new FormData();
    body.append("image", image);
    const xml = $("analyze-xml").files[0];
    if (xml) body.append("labels", xml);
    const time = $("analyze-time").value.trim();
    if (time) body.append("acquired_at", time);
    selectedSample = null;
    $("analyze-samples").querySelectorAll("button[data-sample]").forEach((el) => el.classList.remove("on"));
    postAnalyze("/api/imagery/analyze", body);
  });
  $("analyze-drop").addEventListener("click", () => $("analyze-image").click());
  $("analyze-drop").addEventListener("dragover", (event) => { event.preventDefault(); $("analyze-drop").classList.add("on"); });
  $("analyze-drop").addEventListener("dragleave", () => $("analyze-drop").classList.remove("on"));
  $("analyze-drop").addEventListener("drop", (event) => {
    event.preventDefault();
    $("analyze-drop").classList.remove("on");
    const file = event.dataTransfer.files[0];
    if (file) {
      const dt = new DataTransfer();
      dt.items.add(file);
      $("analyze-image").files = dt.files;
    }
  });
  $("analyze-samples").addEventListener("click", (event) => {
    const btn = event.target.closest("[data-sample]");
    if (!btn) return;
    selectedSample = btn.dataset.sample;
    $("analyze-samples").querySelectorAll("button[data-sample]").forEach((el) => {
      el.classList.toggle("on", el.dataset.sample === selectedSample);
    });
    postAnalyze(`/api/imagery/samples/${encodeURIComponent(btn.dataset.sample)}/analyze`);
  });
  $("analyze-show-rejected").addEventListener("change", draw);
  $("analyze-show-labels").addEventListener("change", draw);
  $("analyze-compare").addEventListener("change", (event) => {
    compare = event.target.checked;
    $("analyze-slider").hidden = !compare;
    draw();
  });
  $("analyze-table").addEventListener("click", (event) => {
    const th = event.target.closest("th");
    if (th && th.dataset.k) { sortKey = th.dataset.k; renderTable(); return; }
    const tr = event.target.closest("tr[data-id]");
    if (!tr || !result) return;
    selectDet(result.detections.find((d) => d.id === tr.dataset.id));
  });
  const canvas = $("analyze-canvas");
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    cam.scale = Math.min(12, Math.max(0.4, cam.scale * (event.deltaY > 0 ? 0.9 : 1.1)));
    draw();
  }, { passive: false });
  canvas.addEventListener("mousedown", (event) => {
    const rect = canvas.getBoundingClientRect();
    if (compare) {
      const split = rect.width * slider;
      if (Math.abs(event.clientX - rect.left - split) < 8) {
        splitDrag = true;
        return;
      }
    }
    drag = { x: event.clientX - cam.x, y: event.clientY - cam.y };
  });
  window.addEventListener("mouseup", () => { drag = null; splitDrag = false; });
  canvas.addEventListener("mousemove", (event) => {
    const rect = canvas.getBoundingClientRect();
    if (splitDrag) {
      slider = Math.min(0.95, Math.max(0.05, (event.clientX - rect.left) / rect.width));
      draw();
      return;
    }
    if (compare) {
      const split = rect.width * slider;
      canvas.style.cursor = Math.abs(event.clientX - rect.left - split) < 8 ? "ew-resize" : "grab";
    } else {
      canvas.style.cursor = "grab";
    }
    if (drag) {
      cam.x = event.clientX - drag.x;
      cam.y = event.clientY - drag.y;
      draw();
      return;
    }
    const det = hitTest(event.clientX - rect.left, event.clientY - rect.top);
    const tip = $("analyze-tooltip");
    if (!det) { tip.hidden = true; return; }
    tip.hidden = false;
    tip.style.left = `${event.clientX - rect.left + 8}px`;
    tip.style.top = `${event.clientY - rect.top + 8}px`;
    const ais = det.ais && det.ais.status === "matched" ? `${det.ais.name || det.ais.mmsi} ${det.ais.match_km} km` : "";
    tip.textContent = `${det.id}  ${(det.score ?? 0).toFixed(2)}  ${det.length_m} m  ${ais}`;
  });
  canvas.addEventListener("click", (event) => {
    const rect = canvas.getBoundingClientRect();
    const det = hitTest(event.clientX - rect.left, event.clientY - rect.top);
    if (det) selectDet(det);
  });
  canvas.addEventListener("dblclick", () => { resetViewer(); draw(); });
  $("analyze-globe").addEventListener("click", () => {
    if (!result || !result.bbox) return;
    onShowGlobe(result);
  });
  window.addEventListener("hashchange", () => {
    if (location.hash === "#analyze") openAnalyze();
    else if (isAnalyzeOpen()) closeAnalyze();
  });
  if (location.hash === "#analyze") openAnalyze();
  window.addEventListener("resize", () => { if (lookImg) draw(); });
}

export function showAnalysisOnGlobe(data) {
  closeAnalyze();
  const [west, south, east, north] = data.bbox;
  const rect = Cesium.Rectangle.fromDegrees(west, south, east, north);
  state.viewer.trackedEntity = undefined;
  state.viewer.camera.flyTo({
    destination: rect,
    duration: 2.5,
    easingFunction: Cesium.EasingFunction.CUBIC_IN_OUT,
  });
  showUploadDetections(data);
  setExtraExclude(data.bbox);
}
