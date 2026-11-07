"""Marine protected areas.

The demo subset is Natura 2000 from the European Environment Agency (open).
Protected Planet / WDPA is optional and needs WDPA_API_TOKEN because the
download is account-gated. scripts/fetch_mpas.py wraps both.
"""

from __future__ import annotations

import math
from typing import Iterable

import httpx
from shapely.geometry import Point, shape

from darkwatch import config

EEA_QUERY = (
    "https://bio.discomap.eea.europa.eu/arcgis/rest/services/"
    "ProtectedSites/Natura2000Sites/MapServer/2/query"
)


def fetch_natura2000(bbox: tuple[float, float, float, float], max_pages: int = 12) -> dict:
    west, south, east, north = bbox
    features: list[dict] = []
    offset = 0
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for _ in range(max_pages):
            params = {
                "where": "1=1",
                "geometry": f"{west},{south},{east},{north}",
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "SITECODE,SITENAME,MS,SITETYPE,Area_km2",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
                "resultOffset": str(offset),
                "resultRecordCount": "20",
            }
            response = client.get(EEA_QUERY, params=params)
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                raise RuntimeError(str(payload["error"]))
            page = payload.get("features") or []
            features.extend(page)
            if not payload.get("exceededTransferLimit") or not page:
                break
            offset += len(page)
    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "source": "EEA Natura 2000 (Habitats and Birds Directive sites)",
            "url": EEA_QUERY,
            "note": "Open protected-area subset for European waters. Not the full WDPA.",
        },
    }


def fetch_wdpa(bbox: tuple[float, float, float, float], token: str) -> dict:
    """Best-effort Protected Planet search. The public API requires a token."""
    west, south, east, north = bbox
    url = "https://api.protectedplanet.net/v3/protected_areas/search"
    params = {
        "marine": "true",
        "token": token,
        "bbox": f"{west},{south},{east},{north}",
        "per_page": "25",
    }
    response = httpx.get(url, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def simplify_collection(fc: dict, tolerance: float = 0.004) -> dict:
    features = []
    for feat in fc.get("features") or []:
        geom = feat.get("geometry")
        if not geom:
            continue
        try:
            g = shape(geom)
            if not g.is_valid:
                g = g.buffer(0)
            g = g.simplify(tolerance, preserve_topology=True)
        except Exception:
            continue
        if g.is_empty:
            continue
        props = dict(feat.get("properties") or {})
        props["source"] = "EEA Natura 2000"
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": props.get("SITENAME") or props.get("name") or "Protected area",
                    "code": props.get("SITECODE") or props.get("code"),
                    "country": props.get("MS") or props.get("country"),
                    "area_km2": props.get("Area_km2"),
                    "source": "EEA Natura 2000",
                },
                "geometry": g.__geo_interface__,
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": fc.get("properties") or {},
    }


def _km(lat: float, lon: float, geom) -> float:
    # Degree distance is enough to rank "inside / nearby" for a demo.
    deg = geom.distance(Point(lon, lat))
    return deg * 111.32 * max(0.2, abs(math.cos(math.radians(lat))))


def annotate_mpa(rows: Iterable[dict], fc: dict) -> list[dict]:
    prepared = []
    for feat in (fc or {}).get("features") or []:
        try:
            geom = shape(feat["geometry"])
            if not geom.is_valid:
                geom = geom.buffer(0)
        except Exception:
            continue
        prepared.append((feat.get("properties") or {}, geom))
    out = []
    for row in rows:
        item = dict(row)
        pt = Point(float(item["lon"]), float(item["lat"]))
        inside_name = None
        nearest_name = None
        nearest_km = None
        for props, geom in prepared:
            name = props.get("name") or props.get("SITENAME") or "Protected area"
            if geom.covers(pt):
                inside_name = name
                nearest_name = name
                nearest_km = 0.0
                break
            dist = _km(float(item["lat"]), float(item["lon"]), geom)
            if nearest_km is None or dist < nearest_km:
                nearest_km = dist
                nearest_name = name
        item["in_mpa"] = inside_name is not None
        item["near_mpa"] = inside_name is not None or (nearest_km is not None and nearest_km <= 5)
        item["mpa_name"] = inside_name or nearest_name
        item["mpa_km"] = None if nearest_km is None else round(nearest_km, 2)
        out.append(item)
    return out


def wdpa_token() -> str:
    return config.wdpa_api_token()
