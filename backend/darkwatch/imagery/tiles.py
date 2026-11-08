"""Planetary Computer TileJSON for the packaged Kattegat scene.

Rendering (VV grayscale in dB, matching ``scene_preview.png``):
  assets=vv
  asset_as_band=True
  expression=10*log10(vv)     # RTC is linear power; scene_step uses the same 10 log10
  rescale=-25,0               # fallback stretch in scene_step when percentiles fail;
                              # typical open-water VV is about −25 to 0 dB
  colormap_name=gray

The STAC item's default tilejson asset is a false-color VV+VH composite. We
rewrite the query rather than using that default.
Native 10 m at 57°N is about WebMercator z=13; we cap maxzoom there.
"""

from __future__ import annotations

import json
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from darkwatch import paths

STAC_ITEM = "https://planetarycomputer.microsoft.com/api/stac/v1/collections/{collection}/items/{item}"
PC_TILEJSON = "https://planetarycomputer.microsoft.com/api/data/v1/item/tilejson.json"
ATTRIBUTION = (
    "Contains modified Copernicus Sentinel data 2026, processed by ESA. "
    "Tiles via Microsoft Planetary Computer."
)
MEMORY_TTL_S = 30 * 60
NATIVE_MAXZOOM = 13
RENDER = {
    "assets": "vv",
    "asset_as_band": "True",
    "expression": "10*log10(vv)",
    "rescale": "-25,0",
    "colormap_name": "gray",
    "format": "png",
}

_memory: dict | None = None
_memory_at: float = 0.0


def _rewrite_tilejson_url(href: str) -> str:
    parsed = urlparse(href)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key in list(query):
        if key in ("assets", "expression", "rescale", "colormap_name", "asset_as_band", "format"):
            query.pop(key, None)
    query.update(RENDER)
    return urlunparse(parsed._replace(query=urlencode(query)))


def _from_disk() -> dict | None:
    path = paths.scene_tiles_cache()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _to_disk(payload: dict) -> None:
    path = paths.scene_tiles_cache()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def fetch_live() -> dict:
    meta = json.loads((paths.demo_dir() / "scene_meta.json").read_text())
    scene_id = meta["scene_id"]
    collection = meta.get("collection") or "sentinel-1-rtc"
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        item = client.get(STAC_ITEM.format(collection=collection, item=scene_id))
        item.raise_for_status()
        assets = item.json().get("assets") or {}
        href = (assets.get("tilejson") or {}).get("href") or (
            f"{PC_TILEJSON}?collection={collection}&item={scene_id}&assets=vv"
        )
        tilejson_url = _rewrite_tilejson_url(href)
        tj = client.get(tilejson_url)
        tj.raise_for_status()
        body = tj.json()
    tiles = body.get("tiles") or []
    if not tiles:
        raise RuntimeError("TileJSON had no tiles")
    template = tiles[0]
    maxzoom = int(body.get("maxzoom") or NATIVE_MAXZOOM)
    payload = {
        "template": template,
        "minzoom": int(body.get("minzoom") or 0),
        "maxzoom": min(maxzoom, NATIVE_MAXZOOM),
        "bounds": body.get("bounds") or meta.get("bbox"),
        "attribution": ATTRIBUTION,
        "scene_id": scene_id,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return payload


def load() -> dict:
    global _memory, _memory_at
    now = time.time()
    if _memory and now - _memory_at < MEMORY_TTL_S:
        return _memory
    try:
        payload = fetch_live()
        _to_disk(payload)
        _memory = payload
        _memory_at = now
        return payload
    except Exception:
        cached = _from_disk()
        if cached:
            _memory = cached
            _memory_at = now
            return cached
        raise
