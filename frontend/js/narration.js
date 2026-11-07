import { $ , esc, toast } from "./ui/dom.js";

export async function playNarration(which, detId) {
  const url = "/api/narrate?which=" + encodeURIComponent(which || "opening") + (detId ? "&det_id=" + encodeURIComponent(detId) : "");
  let data;
  try {
    const response = await fetch(url, { method: "POST" });
    data = await response.json();
    if (!response.ok) throw new Error(data.error || data.detail || response.statusText);
  } catch (err) {
    toast(err.message, "/api/narrate");
    return;
  }
  $("detail-title").textContent = "NARRATION";
  $("detail-body").innerHTML =
    `<p>${esc(data.text)}</p>` +
    `<p class="hint">Voice: ${esc(data.provider)}${data.reason ? " — " + esc(data.reason) : ""}${data.error ? " — " + esc(data.error) : ""}</p>`;
  if (data.audio_url) {
    const audio = new Audio(data.audio_url);
    audio.play();
    return;
  }
  if (window.speechSynthesis) {
    const utter = new SpeechSynthesisUtterance(data.text);
    utter.rate = 0.96;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utter);
    $("detail-body").insertAdjacentHTML("beforeend", "<p class='hint'>Playing the browser voice. This is not Fish Audio.</p>");
  }
}
