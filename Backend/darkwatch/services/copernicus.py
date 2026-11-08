"""Sentinel-1 GRD through Copernicus Data Space Sentinel Hub.

The Copernicus Browser share URL is a visualization reference only. Its
``layerId`` is a Browser preset, not a layer in an OGC WMS instance, and the
encrypted ``visualizationUrl`` is not a tile endpoint.

This module uses the documented Catalog and Process APIs:

- Catalog: https://sh.dataspace.copernicus.eu/catalog/v1/search
- Process: https://sh.dataspace.copernicus.eu/process/v1
- OAuth: https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token

Rendering follows the Sentinel Hub S1GRD example for orthorectified gamma0
in decibels (−20 dB to 0 dB), which is the same product family as the Browser
preset ``IW-DV-VV-DECIBEL-GAMMA0-ORTHORECTIFIED``. Display gamma stays in the
viewer. Credentials stay in the server environment.
"""

from __future__ import annotations

import hashlib
import math
import struct
import threading
import time
import zlib
from datetime import datetime, timedelta, timezone

import httpx

from darkwatch import config, paths

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CATALOG_URL = "https://sh.dataspace.copernicus.eu/catalog/v1/search"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/process/v1"
COLLECTION = "sentinel-1-grd"
CRS_4326 = "http://www.opengis.net/def/crs/EPSG/0/4326"
SETUP = (
    "Copernicus imagery is off until CDSE_CLIENT_ID and CDSE_CLIENT_SECRET are set in the local .env file. "
    "Sign in at https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings "
    "and create a confidential OAuth client (User settings, OAuth clients, grant type Client credentials). "
    "Restart the server after saving. Do not paste the secret into chat."
)
NOTE_ON = (
    "Historical ship data matches this acquisition. "
    "Red points are SAR detections not on public AIS. "
    "Green points are SAR detections matched to AIS. "
    "Gray lines are AIS positions at the packaged scene time, not live ships."
)
NOTE_OFF = (
    "No historical AIS or detections are stored for this acquisition. "
    "Ship overlays stay hidden so current positions are not shown as observations of this pass."
)
NO_COVERAGE = "No Sentinel-1 IW acquisitions in this view for the selected dates."
_BANDS = {
    "DV": ("VV", "VH"),
    "DH": ("HH", "HV"),
    "SV": ("VV",),
    "SH": ("HH",),
    "VV": ("VV",),
    "VH": ("VH",),
    "HH": ("HH",),
    "HV": ("HV",),
}
_VIZ_LABELS = {
    "VV": "VV · decibel gamma0",
    "VH": "VH · decibel gamma0",
    "HH": "HH · decibel gamma0",
    "HV": "HV · decibel gamma0",
    "VVVH": "VV / VH composite",
    "HHHV": "HH / HV composite",
}
_DB_FN = """
function toDb(linear) {
  // Sentinel Hub S1GRD example: −20 dB .. 0 dB mapped to 0 .. 1.
  return Math.max(0, Math.log(linear) * 0.21714724095 + 1);
}
"""
_token_lock = threading.Lock()
_token = {"value": "", "exp": 0.0}
_png_lock = threading.Lock()
_blank_png: bytes | None = None


class Unconfigured(RuntimeError):
    pass


class UpstreamError(RuntimeError):
    pass


def configured() -> bool:
    return config.copernicus_configured()


def visualizations_for(polarization: str) -> list[dict]:
    bands = _BANDS.get((polarization or "").upper(), ())
    if not bands:
        return []
    rows = [{"id": band, "label": _VIZ_LABELS[band]} for band in bands]
    if bands == ("VV", "VH"):
        rows.append({"id": "VVVH", "label": _VIZ_LABELS["VVVH"]})
    elif bands == ("HH", "HV"):
        rows.append({"id": "HHHV", "label": _VIZ_LABELS["HHHV"]})
    return rows


def default_visualization(polarization: str) -> str | None:
    rows = visualizations_for(polarization)
    if not rows:
        return None
    prefer = "VV" if any(row["id"] == "VV" for row in rows) else rows[0]["id"]
    return prefer


def polarization_code(properties: dict) -> str:
    raw = properties.get("s1:polarization") or properties.get("sar:polarization") or ""
    code = str(raw).upper()
    if code in _BANDS:
        return code
    listed = properties.get("sar:polarizations") or properties.get("polarizations") or []
    if isinstance(listed, str):
        listed = [part.strip() for part in listed.split(",") if part.strip()]
    bands = {str(part).upper() for part in listed}
    if {"VV", "VH"} <= bands:
        return "DV"
    if {"HH", "HV"} <= bands:
        return "DH"
    for name in ("VV", "VH", "HH", "HV"):
        if name in bands:
            return name
    return ""


def evalscript(viz: str) -> str:
    if viz in ("VV", "VH", "HH", "HV"):
        return (
            "//VERSION=3\n"
            "function setup() {\n"
            f'  return {{ input: ["{viz}", "dataMask"], output: {{ bands: 4 }} }};\n'
            "}\n"
            "function evaluatePixel(samples) {\n"
            f"  var v = toDb(samples.{viz});\n"
            "  return [v, v, v, samples.dataMask];\n"
            "}\n"
            f"{_DB_FN}"
        )
    if viz == "VVVH":
        pair = ("VV", "VH")
    elif viz == "HHHV":
        pair = ("HH", "HV")
    else:
        raise ValueError(f"unsupported visualization {viz}")
    red, green = pair
    return (
        "//VERSION=3\n"
        "function setup() {\n"
        f'  return {{ input: ["{red}", "{green}", "dataMask"], output: {{ bands: 4 }} }};\n'
        "}\n"
        "function evaluatePixel(samples) {\n"
        f"  var a = toDb(samples.{red});\n"
        f"  var b = toDb(samples.{green});\n"
        "  return [a, b, a / b / 10, samples.dataMask];\n"
        "}\n"
        f"{_DB_FN}"
    )


def tile_bbox(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """XYZ Web Mercator tile as west, south, east, north in degrees."""
    if z < 0 or z > 22:
        raise ValueError("zoom out of range")
    n = 2**z
    if x < 0 or y < 0 or x >= n or y >= n:
        raise ValueError("tile index out of range")

    def lon(px: int) -> float:
        return px / n * 360.0 - 180.0

    def lat(py: int) -> float:
        merc = math.pi * (1 - 2 * py / n)
        return math.degrees(math.atan(math.sinh(merc)))

    west, east = lon(x), lon(x + 1)
    north, south = lat(y), lat(y + 1)
    return west, south, east, north


def bboxes_overlap(a: list[float] | tuple, b: list[float] | tuple) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def _parse_time(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def historical_ships(acquisition: dict, scene: dict | None) -> dict:
    """Ship overlays exist only for the packaged scene, never for 'now'."""
    if not scene:
        return {"available": False, "scene_time": None, "note": NOTE_OFF}
    try:
        start = _parse_time(scene["start"])
        end = _parse_time(scene["end"])
        instant = _parse_time(acquisition["datetime"])
        scene_box = scene["bbox"]
        acq_box = acquisition["bbox"]
    except (KeyError, TypeError, ValueError):
        return {"available": False, "scene_time": scene.get("scene_time"), "note": NOTE_OFF}
    slack = timedelta(minutes=5)
    hits_time = (start - slack) <= instant <= (end + slack)
    hits_box = bboxes_overlap(acq_box, scene_box)
    scene_time = scene.get("scene_time")
    if hits_time and hits_box:
        note = NOTE_ON
        if scene_time:
            note = f"{NOTE_ON} Packaged scene {scene_time}."
        return {"available": True, "scene_time": scene_time, "note": note}
    return {"available": False, "scene_time": scene_time, "note": NOTE_OFF}


def scene_window(meta: dict | None, summary: dict | None) -> dict | None:
    if not meta or not meta.get("bbox"):
        return None
    start = meta.get("start_datetime") or meta.get("datetime")
    end = meta.get("end_datetime") or meta.get("datetime")
    if not start or not end:
        return None
    scene_time = None
    if summary:
        scene_time = summary.get("scene_time")
    scene_time = scene_time or meta.get("datetime")
    return {"start": start, "end": end, "bbox": list(meta["bbox"]), "scene_time": scene_time}


def view_size(west: float, south: float, east: float, north: float, max_edge: int = 640) -> tuple[int, int]:
    """One image for the view. The long side stays small so a pass returns in one request."""
    lon = max(east - west, 1e-6)
    lat = max(north - south, 1e-6)
    mid = math.radians((south + north) / 2.0)
    aspect = (lon * max(math.cos(mid), 0.2)) / lat
    if aspect >= 1:
        width = max_edge
        height = max(64, int(round(max_edge / aspect)))
    else:
        height = max_edge
        width = max(64, int(round(max_edge * aspect)))
    return width, height


def process_request(
    bbox: tuple[float, float, float, float] | list[float],
    start: datetime,
    end: datetime,
    polarization: str,
    viz: str,
    orbit: str | None,
    zoom: int,
    width: int = 256,
    height: int = 256,
) -> dict:
    if viz not in {row["id"] for row in visualizations_for(polarization)}:
        raise ValueError(f"{viz} is not available for polarization {polarization}")
    data_filter = {
        "timeRange": {"from": _iso(start), "to": _iso(end)},
        "acquisitionMode": "IW",
        "polarization": polarization,
        "mosaickingOrder": "mostRecent",
    }
    if orbit in ("ASCENDING", "DESCENDING"):
        data_filter["orbitDirection"] = orbit
    # Resolution is a dataFilter, not a processing option. HIGH is ~10 m IW.
    data_filter["resolution"] = "HIGH" if zoom >= 10 else "MEDIUM"
    return {
        "input": {
            "bounds": {"bbox": [bbox[0], bbox[1], bbox[2], bbox[3]], "properties": {"crs": CRS_4326}},
            "data": [
                {
                    "type": COLLECTION,
                    "dataFilter": data_filter,
                    "processing": {
                        "backCoeff": "GAMMA0_ELLIPSOID",
                        "orthorectify": "true",
                    },
                }
            ],
        },
        "output": {
            "width": width,
            "height": height,
            "responses": [{"identifier": "default", "format": {"type": "image/png"}}],
        },
        "evalscript": evalscript(viz),
    }


def _safe_message(response: httpx.Response, secret: str) -> str:
    detail = ""
    try:
        body = response.json()
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                detail = str(error.get("message") or error.get("description") or "")
            elif isinstance(error, str):
                detail = error
            detail = detail or str(body.get("detail") or body.get("message") or "")
    except Exception:
        detail = ""
    detail = " ".join(detail.split())[:240]
    if secret and secret in detail:
        detail = "upstream rejected the request"
    if not detail:
        detail = f"Copernicus returned HTTP {response.status_code}"
    return detail


def _access_token(client: httpx.Client) -> str:
    now = time.time()
    with _token_lock:
        if _token["value"] and now < _token["exp"]:
            return _token["value"]
        secret = config.cdse_client_secret()
        response = client.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": config.cdse_client_id(),
                "client_secret": secret,
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        if response.status_code != 200:
            raise UpstreamError(f"Copernicus authentication failed. {_safe_message(response, secret)}")
        payload = response.json()
        token = payload.get("access_token") or ""
        if not token:
            raise UpstreamError("Copernicus authentication failed.")
        expires = float(payload.get("expires_in") or 300)
        _token["value"] = token
        _token["exp"] = now + max(30.0, expires - 60.0)
        return token


def _auth_headers(client: httpx.Client) -> dict[str, str]:
    return {"Authorization": f"Bearer {_access_token(client)}"}


def _normalize_feature(feature: dict, scene: dict | None) -> dict | None:
    props = feature.get("properties") or {}
    mode = str(props.get("sar:instrument_mode") or props.get("instrument_mode") or "IW").upper()
    if mode and mode != "IW":
        return None
    when = props.get("datetime") or feature.get("datetime")
    if not when:
        return None
    bbox = feature.get("bbox") or props.get("bbox")
    if not bbox or len(bbox) != 4:
        return None
    polarization = polarization_code(props)
    start = props.get("start_datetime") or when
    end = props.get("end_datetime") or when
    orbit = str(props.get("sat:orbit_state") or "").lower()
    if orbit not in ("ascending", "descending"):
        orbit = ""
    instant = _parse_time(str(when))
    row = {
        "id": str(feature.get("id") or f"{when}:{bbox[0]:.4f}"),
        "datetime": _iso(instant),
        "start": _iso(_parse_time(str(start))),
        "end": _iso(_parse_time(str(end))),
        "platform": props.get("platform") or props.get("constellation") or "",
        "orbit": orbit,
        "polarization": polarization,
        "visualizations": visualizations_for(polarization),
        "bbox": [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])],
    }
    row["ships"] = historical_ships(row, scene)
    return row


def search_acquisitions(
    west: float,
    south: float,
    east: float,
    north: float,
    start: datetime,
    end: datetime,
    scene: dict | None,
) -> tuple[list[dict], bool]:
    if not configured():
        raise Unconfigured(SETUP)
    if east <= west or north <= south:
        raise ValueError("Draw a view that does not cross the antimeridian.")
    if end < start:
        raise ValueError("The end date is before the start date.")
    if end - start > timedelta(days=31):
        raise ValueError("Search at most 31 days at a time.")
    body = {
        "bbox": [west, south, east, north],
        "datetime": f"{_iso(start)}/{_iso(end)}",
        "collections": [COLLECTION],
        "limit": 100,
        "filter": "sar:instrument_mode = 'IW'",
        "filter-lang": "cql2-text",
    }
    secret = config.cdse_client_secret()
    with httpx.Client(timeout=45.0) as client:
        headers = {**_auth_headers(client), "Content-Type": "application/json"}
        response = client.post(CATALOG_URL, json=body, headers=headers)
        if response.status_code == 400:
            body.pop("filter", None)
            body.pop("filter-lang", None)
            response = client.post(CATALOG_URL, json=body, headers=headers)
        if response.status_code != 200:
            raise UpstreamError(_safe_message(response, secret))
        payload = response.json()
    features = payload.get("features") or []
    rows = []
    seen = set()
    for feature in features:
        row = _normalize_feature(feature, scene)
        if row is None or row["id"] in seen:
            continue
        seen.add(row["id"])
        rows.append(row)
    rows.sort(key=lambda row: row["datetime"], reverse=True)
    matched = payload.get("numberMatched")
    try:
        matched_n = int(matched) if matched is not None else 0
    except (TypeError, ValueError):
        matched_n = 0
    truncated = len(features) >= 100 or matched_n > len(rows)
    return rows[:100], truncated


def transparent_png(size: int = 256) -> bytes:
    global _blank_png
    with _png_lock:
        if _blank_png is not None and size == 256:
            return _blank_png

        def chunk(tag: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

        raw = b"".join(b"\x00" + (b"\x00\x00\x00\x00" * size) for _ in range(size))
        png = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b"")
        )
        if size == 256:
            _blank_png = png
        return png


def _cache_path(key: str):
    folder = paths.cache_dir() / "copernicus"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{key}.png"


def _prepare_window(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    if end < start or end - start > timedelta(minutes=30):
        raise ValueError("The acquisition window must be at most 30 minutes.")
    if end - start < timedelta(seconds=2):
        start -= timedelta(seconds=1)
        end += timedelta(seconds=1)
    return start, end


def _fetch_png(payload: dict, *, empty_on_400: bool) -> bytes:
    secret = config.cdse_client_secret()
    with httpx.Client(timeout=90.0) as client:
        headers = {**_auth_headers(client), "Content-Type": "application/json", "Accept": "image/png"}
        response = client.post(PROCESS_URL, json=payload, headers=headers)
        if empty_on_400 and response.status_code == 400:
            return transparent_png()
        if response.status_code != 200 or not response.content.startswith(b"\x89PNG"):
            raise UpstreamError(_safe_message(response, secret))
        return response.content


def render_view(
    west: float,
    south: float,
    east: float,
    north: float,
    start: datetime,
    end: datetime,
    polarization: str,
    viz: str,
    orbit: str | None,
    footprint: list[float],
) -> bytes:
    """Render the visible part of one pass as a single PNG."""
    if not configured():
        raise Unconfigured(SETUP)
    start, end = _prepare_window(start, end)
    box = (west, south, east, north)
    if east <= west or north <= south or not bboxes_overlap(box, footprint):
        return transparent_png(64)
    width, height = view_size(west, south, east, north)
    span = max(east - west, north - south)
    zoom = 11 if span <= 0.2 else 8
    digest = hashlib.sha256(
        f"view|{west:.4f}|{south:.4f}|{east:.4f}|{north:.4f}|{width}|{height}|"
        f"{_iso(start)}|{_iso(end)}|{polarization}|{viz}|{orbit or ''}".encode()
    ).hexdigest()
    cached = _cache_path(digest)
    if cached.is_file() and cached.stat().st_size > 8:
        return cached.read_bytes()
    payload = process_request(box, start, end, polarization, viz, orbit, zoom, width, height)
    png = _fetch_png(payload, empty_on_400=False)
    if png.startswith(b"\x89PNG"):
        cached.write_bytes(png)
    return png


def render_tile(
    z: int,
    x: int,
    y: int,
    start: datetime,
    end: datetime,
    polarization: str,
    viz: str,
    orbit: str | None,
    footprint: list[float],
) -> bytes:
    if not configured():
        raise Unconfigured(SETUP)
    start, end = _prepare_window(start, end)
    # Low zoom tiles cover hundreds of kilometres and make Sentinel Hub reject the request.
    if z < 8:
        return transparent_png()
    bbox = tile_bbox(z, x, y)
    if not bboxes_overlap(bbox, footprint):
        return transparent_png()
    digest = hashlib.sha256(
        f"{z}/{x}/{y}|{_iso(start)}|{_iso(end)}|{polarization}|{viz}|{orbit or ''}".encode()
    ).hexdigest()
    cached = _cache_path(digest)
    if cached.is_file() and cached.stat().st_size > 8:
        return cached.read_bytes()
    payload = process_request(bbox, start, end, polarization, viz, orbit, z)
    png = _fetch_png(payload, empty_on_400=True)
    if png != transparent_png():
        cached.write_bytes(png)
    return png
