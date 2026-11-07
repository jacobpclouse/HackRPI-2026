export function $(id) {
  return document.getElementById(id);
}

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

export function toast(message, route) {
  const box = $("toasts");
  if (!box) return;
  while (box.children.length >= 3) box.firstChild.remove();
  const el = document.createElement("div");
  el.className = "toast";
  el.innerHTML = `<span class="micro">${esc(route || "error")}</span><p>${esc(message)}</p>`;
  box.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}
