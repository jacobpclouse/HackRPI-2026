import { beginScrub, clockDate, endScrub, setTime } from "./clock.js";
import { state } from "./state.js";
import { $ } from "./ui/dom.js";

const coverage = "#5ac8fa";
const gap = "#f5a524";
const text2 = "#8a94a3";
const text3 = "#545e6c";

let windowStart = 0;
let windowEnd = 0;
let dragging = false;

function hatch(ctx) {
  const c = document.createElement("canvas");
  c.width = 8;
  c.height = 8;
  const g = c.getContext("2d");
  g.strokeStyle = "rgba(245,165,36,0.45)";
  g.lineWidth = 1;
  g.beginPath();
  g.moveTo(0, 8);
  g.lineTo(8, 0);
  g.stroke();
  return ctx.createPattern(c, "repeat");
}

export function drawTimeline(data, title) {
  state.coverage = data;
  $("tl-title").textContent = title;
  const longest = data.longest_gap;
  $("tl-gap").textContent = longest ? longest.label : "No gap in this window";
  const tasked = data.longest_gap_if_all_tasked;
  $("tl-note").textContent =
    `${data.systematic_pass_count} systematic passes, ${data.possible_pass_count} possible tasked accesses. ` +
    (tasked ? `If every tasked access were an image, the longest hole would be ${tasked.label.replace("no systematic swath for ", "")}. ` : "") +
    (data.note || "");
  windowStart = Date.parse(data.start);
  windowEnd = Date.parse(data.end);
  paint();
}

export function paint() {
  const canvas = $("tl-canvas");
  const data = state.coverage;
  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth || canvas.parentElement.clientWidth || 800;
  const cssH = 72;
  canvas.width = Math.floor(cssW * dpr);
  canvas.height = Math.floor(cssH * dpr);
  canvas.style.width = cssW + "px";
  canvas.style.height = cssH + "px";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);
  ctx.fillStyle = "#0a0e13";
  ctx.fillRect(0, 18, cssW, 28);
  ctx.strokeStyle = "#1b222c";
  ctx.strokeRect(0.5, 18.5, cssW - 1, 27);
  if (!data || !windowEnd) {
    ctx.fillStyle = text3;
    ctx.font = "11px JetBrains Mono, monospace";
    ctx.fillText("No coverage window", 8, 36);
    return;
  }
  const span = Math.max(1, windowEnd - windowStart);
  const xOf = (isoOrMs) => {
    const t = typeof isoOrMs === "number" ? isoOrMs : Date.parse(isoOrMs);
    return ((t - windowStart) / span) * cssW;
  };
  ctx.fillStyle = hatch(ctx);
  for (const g of data.gaps || []) {
    const x0 = xOf(g.start);
    const x1 = xOf(g.end);
    ctx.fillRect(x0, 18, Math.max(1, x1 - x0), 28);
  }
  const longest = data.longest_gap;
  if (longest) {
    const mid = (xOf(longest.start) + xOf(longest.end)) / 2;
    ctx.fillStyle = gap;
    ctx.font = "11px JetBrains Mono, monospace";
    ctx.fillText(longest.label.replace("no systematic swath for ", ""), Math.min(cssW - 80, Math.max(4, mid - 30)), 14);
  }
  const passes = state.layers.possible ? data.passes : (data.passes || []).filter((p) => p.coverage === "systematic");
  for (const pass of passes || []) {
    const x = xOf(pass.center);
    ctx.fillStyle = pass.coverage === "systematic" ? coverage : "rgba(90,200,250,0.4)";
    ctx.fillRect(x, 20, 2, 24);
  }
  if (data.observed) {
    const x = xOf(data.observed);
    ctx.fillStyle = "#ff4d4f";
    ctx.fillRect(x, 18, 2, 28);
    ctx.fillStyle = "#ff4d4f";
    ctx.font = "10px JetBrains Mono, monospace";
    ctx.fillText("OBSERVED", Math.min(cssW - 64, x + 4), 66);
  }
  ctx.fillStyle = text2;
  ctx.font = "10px JetBrains Mono, monospace";
  for (let i = 0; i <= 8; i++) {
    const t = windowStart + (span * i) / 8;
    const date = new Date(t);
    const x = (i / 8) * cssW;
    ctx.fillStyle = "#1b222c";
    ctx.fillRect(x, 18, 1, 28);
    ctx.fillStyle = text3;
    if (i % 2 === 0) {
      ctx.fillText(`${String(date.getUTCHours()).padStart(2, "0")}Z`, Math.min(cssW - 24, x + 2), 66);
    }
  }
  const now = clockDate().getTime();
  if (now >= windowStart && now <= windowEnd) {
    const x = xOf(now);
    ctx.strokeStyle = "#e6eaf0";
    ctx.beginPath();
    ctx.moveTo(x + 0.5, 16);
    ctx.lineTo(x + 0.5, 50);
    ctx.stroke();
  }
}

function timeAt(clientX) {
  const rect = $("tl-canvas").getBoundingClientRect();
  const t = windowStart + ((clientX - rect.left) / rect.width) * (windowEnd - windowStart);
  return new Date(Math.min(windowEnd, Math.max(windowStart, t)));
}

export function bindScrub() {
  const canvas = $("tl-canvas");
  canvas.addEventListener("mousedown", (event) => {
    if (!windowEnd) return;
    dragging = true;
    beginScrub();
    setTime(timeAt(event.clientX));
    paint();
  });
  window.addEventListener("mousemove", (event) => {
    if (!dragging) return;
    setTime(timeAt(event.clientX));
    paint();
  });
  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    endScrub();
  });
  window.addEventListener("resize", paint);
}
