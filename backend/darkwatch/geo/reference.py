"""Packaged Natural Earth layers for the Kattegat report.

Lazy loaders return None when a file is missing. Callers degrade with a
visible note rather than crashing. Jurisdiction is nearest-coastline plus
12 nm, not official maritime boundaries.
"""

from __future__ import annotations

import json
from functools import lru_cache

from pyproj import Geod
from shapely.geometry import Point, shape
from shapely.ops import nearest_points, unary_union

from darkwatch import paths

GEOD = Geod(ellps="WGS84")
TERRITORIAL_KM = 22.2  # 12 nautical miles
JURISDICTION_METHOD = (
    "Approximate: nearest coastline and 12 nm distance. Official maritime boundaries were not computed."
)
COMPASS = (
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
)


def _path(name: str):
    return paths.reference_dir() / name


@lru_cache(maxsize=1)
def load_ports() -> dict | None:
    return _load("ports.geojson")


@lru_cache(maxsize=1)
def load_land() -> dict | None:
    return _load("land.geojson")


@lru_cache(maxsize=1)
def load_countries() -> dict | None:
    return _load("countries.geojson")


def available() -> dict[str, bool]:
    return {
        "ports": _path("ports.geojson").is_file(),
        "land": _path("land.geojson").is_file(),
        "countries": _path("countries.geojson").is_file(),
    }


def _load(name: str) -> dict | None:
    path = _path(name)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        return None
    return data


def clear_cache() -> None:
    load_ports.cache_clear()
    load_land.cache_clear()
    load_countries.cache_clear()
    land_geom.cache_clear()


def geodesic_inv(lon1: float, lat1: float, lon2: float, lat2: float) -> tuple[float, float, float]:
    """Forward azimuth from 1→2 (deg), back azimuth, distance metres."""
    az12, az21, dist = GEOD.inv(lon1, lat1, lon2, lat2)
    return (az12 + 360.0) % 360.0, (az21 + 360.0) % 360.0, dist


def compass_label(bearing_deg: float) -> str:
    idx = int((float(bearing_deg) % 360.0 + 11.25) // 22.5) % 16
    return COMPASS[idx]


@lru_cache(maxsize=1)
def land_geom():
    fc = load_land()
    if not fc:
        return None
    geoms = []
    for feat in fc.get("features") or []:
        try:
            geom = shape(feat.get("geometry"))
        except Exception:
            continue
        if not geom.is_empty:
            geoms.append(geom)
    if not geoms:
        return None
    return unary_union(geoms)


def clip_to_sea(geom):
    """Difference against packaged land. Returns (geom, clipped_bool)."""
    land = land_geom()
    if land is None or geom is None or geom.is_empty:
        return geom, False
    sea = geom.difference(land)
    if sea.is_empty:
        return geom, True
    return sea, True


def jurisdiction(lat: float, lon: float) -> dict | None:
    fc = load_countries()
    if fc is None:
        return None
    pt = Point(lon, lat)
    best = None
    for feat in fc.get("features") or []:
        try:
            geom = shape(feat.get("geometry"))
        except Exception:
            continue
        if geom.is_empty:
            continue
        props = feat.get("properties") or {}
        name = props.get("name") or props.get("admin") or props.get("ADMIN") or props.get("NAME")
        if not name:
            continue
        if geom.covers(pt) or geom.contains(pt):
            dist_km = 0.0
        else:
            nearest = nearest_points(pt, geom)[1]
            _az, _back, metres = geodesic_inv(lon, lat, nearest.x, nearest.y)
            dist_km = metres / 1000.0
        row = {
            "nearest_coast_country": str(name),
            "distance_to_coast_km": round(dist_km, 2),
            "likely_territorial_sea": dist_km <= TERRITORIAL_KM,
            "method": JURISDICTION_METHOD,
        }
        if best is None or dist_km < best["distance_to_coast_km"]:
            best = row
    return best


def nearest_ports(lat: float, lon: float, n: int = 3) -> list[dict] | None:
    fc = load_ports()
    if fc is None:
        return None
    ranked = []
    for feat in fc.get("features") or []:
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates")
        if not coords or len(coords) < 2:
            continue
        plon, plat = float(coords[0]), float(coords[1])
        az, _back, metres = geodesic_inv(plon, plat, lon, lat)
        props = feat.get("properties") or {}
        ranked.append(
            {
                "name": props.get("name") or "Unnamed port",
                "country": props.get("country"),
                "lat": round(plat, 5),
                "lon": round(plon, 5),
                "distance_km": round(metres / 1000.0, 2),
                "bearing_deg": round(az, 1),
                "bearing_compass": compass_label(az),
            }
        )
    ranked.sort(key=lambda row: row["distance_km"])
    return ranked[:n]


def features_in_bounds(fc: dict | None, bounds: tuple[float, float, float, float]) -> list[dict]:
    if not fc:
        return []
    window = box_from_bounds(bounds)
    out = []
    for feat in fc.get("features") or []:
        try:
            geom = shape(feat.get("geometry"))
        except Exception:
            continue
        if geom.is_empty or not geom.intersects(window):
            continue
        clipped = geom.intersection(window)
        if clipped.is_empty:
            continue
        props = dict(feat.get("properties") or {})
        out.append({"geometry": clipped, "properties": props})
    return out


def box_from_bounds(bounds: tuple[float, float, float, float]):
    from shapely.geometry import box

    west, south, east, north = bounds
    return box(west, south, east, north)
