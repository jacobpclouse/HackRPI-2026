export function pad(n) {
  return String(n).padStart(2, "0");
}

export function offsetLabel(ms) {
  const sign = ms < 0 ? "\u2212" : "+";
  const s = Math.floor(Math.abs(ms) / 1000);
  return `T${sign}${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}

export function utcStamp(date) {
  return date.toISOString().slice(11, 19);
}

export function coord(lat, lon) {
  const ns = lat >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(3)}°${ns}  ${Math.abs(lon).toFixed(3)}°${ew}`;
}

export function km(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${Number(value).toFixed(1)} km`;
}

export function hours(seconds) {
  if (seconds == null) return "—";
  return `${(seconds / 3600).toFixed(1)} h`;
}

export function accessChip(access) {
  if (access === "open") return "OPEN";
  if (access === "open-sample") return "SAMPLE";
  if (access === "restricted") return "RESTRICTED";
  if (access === "commercial") return "COMMERCIAL";
  return (access || "").toUpperCase();
}
