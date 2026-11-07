import { toast } from "./ui/dom.js";

export async function getJSON(url) {
  let response;
  try {
    response = await fetch(url);
  } catch (err) {
    toast(err.message || "Network error", url);
    throw err;
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.error || body.detail || detail;
    } catch {
      /* keep status text */
    }
    const error = new Error(detail);
    toast(detail, url.split("?")[0]);
    throw error;
  }
  return response.json();
}
