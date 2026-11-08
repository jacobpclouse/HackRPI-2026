"""Server-rendered report map. Prints without JavaScript."""

from __future__ import annotations

import json
import math
from xml.sax.saxutils import escape

from shapely.geometry import box as shp_box
from shapely.geometry import shape
from shapely.ops import unary_union

from darkwatch import paths
from darkwatch.casefile.facts import DEFAULT_HORIZON_H, build_facts
from darkwatch.casefile.reach import SPEED_KN, geodesic_disk, reach_radius_km
from darkwatch.catalog import get_catalog
from darkwatch.geo.reference import features_in_bounds, load_countries, load_land, load_ports
from darkwatch.orbit.orbit import parse_time
from darkwatch.orbit.passes import swath_polygon

SEA = "#e8eef3"
LAND = "#d5cfc4"
COAST = "#5a564c"
INK = "#1a1d21"
MUTED = "#5c6570"
PROTECTED = "#9b8afb"
GAP = "#f5a524"
COVERAGE = "#5ac8fa"
TARGET = "#ff4d4f"
PORT = "#1a1d21"


class View:
    def __init__(self, lat: float, lon: float, half_lat: float = 0.5, width: int = 760, height: int = 520):
        self.lat0 = lat
        self.lon0 = lon
        self.south = lat - half_lat
        self.north = lat + half_lat
        k = max(0.2, math.cos(math.radians(lat)))
        half_lon = half_lat / k
        self.west = lon - half_lon
        self.east = lon + half_lon
        self.width = width
        self.height = height
        self.pad_l = 52
        self.pad_r = 28
        self.pad_t = 28
        self.pad_b = 56
        self.inner_w = width - self.pad_l - self.pad_r
        self.inner_h = height - self.pad_t - self.pad_b

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return self.west, self.south, self.east, self.north

    def xy(self, lon: float, lat: float) -> tuple[float, float]:
        x = self.pad_l + (lon - self.west) / (self.east - self.west) * self.inner_w
        y = self.pad_t + (self.north - lat) / (self.north - self.south) * self.inner_h
        return x, y

    def clip_window(self):
        return shp_box(self.west, self.south, self.east, self.north)


def _path(geom, view: View) -> str:
    if geom is None or geom.is_empty:
        return ""
    if geom.geom_type == "GeometryCollection":
        return "".join(_path(g, view) for g in geom.geoms)
    if geom.geom_type == "MultiPolygon":
        return "".join(_path(g, view) for g in geom.geoms)
    if geom.geom_type == "Polygon":
        return _ring_path(geom.exterior.coords, view) + "".join(_ring_path(r.coords, view) for r in geom.interiors)
    if geom.geom_type == "LineString":
        return _ring_path(geom.coords, view, close=False)
    if geom.geom_type == "Point":
        x, y = view.xy(geom.x, geom.y)
        return f"M{x:.1f},{y:.1f}"
    return ""


def _ring_path(coords, view: View, close: bool = True) -> str:
    pts = [view.xy(lon, lat) for lon, lat, *_ in ((c if len(c) >= 2 else (0, 0)) for c in coords)]
    if not pts:
        return ""
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}" + "".join(f"L{x:.1f},{y:.1f}" for x, y in pts[1:])
    if close:
        d += "Z"
    return d


def _mpa_union(bounds):
    path = paths.demo_dir() / "mpas.geojson"
    if not path.is_file():
        return None
    try:
        fc = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    geoms = []
    window = shp_box(*bounds)
    for feat in fc.get("features") or []:
        try:
            geom = shape(feat.get("geometry"))
        except Exception:
            continue
        if geom.is_empty or not geom.intersects(window):
            continue
        geoms.append(geom.intersection(window))
    if not geoms:
        return None
    return unary_union(geoms)


def _swath(facts: dict, view: View):
    best = facts.get("best_next")
    if not best:
        return None
    try:
        cat = get_catalog()
        rec = next((s for s in cat.satellites if s.norad == best.get("norad")), None)
        if rec is None:
            return None
        feat = swath_polygon(rec, parse_time(best["start"]))
        geom = shape(feat["geometry"]) if feat.get("geometry") else None
        if geom is None or geom.is_empty:
            return None
        return geom.intersection(view.clip_window())
    except Exception:
        return None


def _scale_km(view: View, km: float = 20.0) -> float:
    lon_km = 111.32 * math.cos(math.radians(view.lat0)) * (view.east - view.west)
    return km / max(lon_km, 1e-6) * view.inner_w


def render_map(facts: dict) -> str:
    tgt = facts.get("target") or {}
    lat, lon = float(tgt["lat"]), float(tgt["lon"])
    view = View(lat, lon)
    notes = list(facts.get("notes") or [])
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {view.width} {view.height}" '
        f'width="{view.width}" height="{view.height}" role="img" '
        f'aria-label="Report map">'
        f"<defs>"
        f'<clipPath id="frame"><rect x="{view.pad_l}" y="{view.pad_t}" width="{view.inner_w}" height="{view.inner_h}"/></clipPath>'
        f'<pattern id="hatch" patternUnits="userSpaceOnUse" width="6" height="6">'
        f'<path d="M0,6 L6,0" stroke="{COVERAGE}" stroke-width="1"/></pattern>'
        f"</defs>",
        f'<rect width="{view.width}" height="{view.height}" fill="#fff"/>',
        f'<rect x="{view.pad_l}" y="{view.pad_t}" width="{view.inner_w}" height="{view.inner_h}" fill="{SEA}" stroke="{INK}" stroke-width="0.8"/>',
        '<g clip-path="url(#frame)">',
    ]
    land_fc = load_land()
    if land_fc is None:
        notes.append("reference layer unavailable: land")
    else:
        for item in features_in_bounds(land_fc, view.bounds):
            d = _path(item["geometry"], view)
            if d:
                parts.append(f'<path d="{d}" fill="{LAND}" stroke="{COAST}" stroke-width="0.8"/>')
    countries = load_countries()
    if countries is None:
        notes.append("reference layer unavailable: countries")
    else:
        for item in features_in_bounds(countries, view.bounds):
            geom = item["geometry"]
            if geom.is_empty:
                continue
            c = geom.representative_point()
            x, y = view.xy(c.x, c.y)
            name = escape(str(item["properties"].get("name") or item["properties"].get("admin") or ""))
            if name:
                parts.append(
                    f'<text x="{x:.1f}" y="{y:.1f}" fill="{MUTED}" font-size="11" '
                    f'font-family="Inter, system-ui, sans-serif" text-anchor="middle">{name}</text>'
                )
    mpa = _mpa_union(view.bounds)
    if mpa is not None and not mpa.is_empty:
        d = _path(mpa, view)
        if d:
            parts.append(f'<path d="{d}" fill="none" stroke="{PROTECTED}" stroke-width="1.4"/>')
    hours = float(((facts.get("search_area") or {}).get("search_box") or {}).get("horizon_h") or DEFAULT_HORIZON_H)
    for key, kn in (("fast", SPEED_KN["fast"]), ("typical", SPEED_KN["typical"]), ("slow", SPEED_KN["slow"])):
        disk = geodesic_disk(lat, lon, reach_radius_km(hours, kn)).intersection(view.clip_window())
        d = _path(disk, view)
        width = {"fast": 0.8, "typical": 1.2, "slow": 1.6}[key]
        if d:
            parts.append(f'<path d="{d}" fill="none" stroke="{GAP}" stroke-width="{width}"/>')
    box = (facts.get("search_area") or {}).get("search_box") or {}
    if box:
        rect = shp_box(box["west"], box["south"], box["east"], box["north"]).intersection(view.clip_window())
        d = _path(rect, view)
        if d:
            parts.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="1.1" stroke-dasharray="4 3"/>')
        for pt in (box.get("corners") or {}).values():
            x, y = view.xy(pt["lon"], pt["lat"])
            parts.append(f'<path d="M{x-5:.1f},{y:.1f}h10M{x:.1f},{y-5:.1f}v10" stroke="{INK}" stroke-width="1"/>')
    swath = _swath(facts, view)
    if swath is not None and not swath.is_empty:
        d = _path(swath, view)
        if d:
            parts.append(f'<path d="{d}" fill="url(#hatch)" stroke="{COVERAGE}" stroke-width="0.8" fill-opacity="0.85"/>')
    ports = facts.get("nearest_ports") or []
    if load_ports() is None:
        notes.append("reference layer unavailable: ports")
    if ports:
        p = ports[0]
        x0, y0 = view.xy(p["lon"], p["lat"])
        x1, y1 = view.xy(lon, lat)
        parts.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{MUTED}" stroke-width="0.8"/>')
        parts.append(f'<circle cx="{x0:.1f}" cy="{y0:.1f}" r="3.2" fill="{PORT}"/>')
        label = escape(f"{p['name']} {p['distance_km']} km {p['bearing_compass']}")
        parts.append(
            f'<text x="{x0 + 6:.1f}" y="{y0 - 6:.1f}" fill="{INK}" font-size="10" '
            f'font-family="JetBrains Mono, ui-monospace, monospace">{label}</text>'
        )
    tx, ty = view.xy(lon, lat)
    parts.append(f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="4" fill="{TARGET}" stroke="{INK}" stroke-width="0.6"/>')
    parts.append("</g>")
    # ticks
    lat0 = math.ceil(view.south * 4) / 4
    while lat0 <= view.north + 1e-9:
        x, y = view.xy(view.west, lat0)
        parts.append(f'<line x1="{view.pad_l - 4}" y1="{y:.1f}" x2="{view.pad_l}" y2="{y:.1f}" stroke="{INK}"/>')
        parts.append(
            f'<text x="{view.pad_l - 6}" y="{y + 3:.1f}" text-anchor="end" fill="{MUTED}" font-size="9" '
            f'font-family="JetBrains Mono, ui-monospace, monospace">{lat0:.2f}°</text>'
        )
        lat0 += 0.25
    lon0 = math.ceil(view.west * 4) / 4
    while lon0 <= view.east + 1e-9:
        x, y = view.xy(lon0, view.south)
        parts.append(f'<line x1="{x:.1f}" y1="{view.pad_t + view.inner_h}" x2="{x:.1f}" y2="{view.pad_t + view.inner_h + 4}" stroke="{INK}"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{view.pad_t + view.inner_h + 14}" text-anchor="middle" fill="{MUTED}" font-size="9" '
            f'font-family="JetBrains Mono, ui-monospace, monospace">{lon0:.2f}°</text>'
        )
        lon0 += 0.25
    # north arrow
    nx = view.pad_l + view.inner_w - 18
    ny = view.pad_t + 22
    parts.append(f'<g id="north"><polygon points="{nx},{ny - 12} {nx - 6},{ny + 8} {nx + 6},{ny + 8}" fill="{INK}"/>')
    parts.append(
        f'<text x="{nx}" y="{ny + 20}" text-anchor="middle" fill="{INK}" font-size="9" '
        f'font-family="Inter, system-ui, sans-serif">N</text></g>'
    )
    # scale bar
    bar = _scale_km(view, 20)
    sx = view.pad_l + 10
    sy = view.pad_t + view.inner_h - 14
    parts.append(f'<g id="scale"><rect x="{sx}" y="{sy}" width="{bar:.1f}" height="3" fill="{INK}"/>')
    parts.append(
        f'<text x="{sx + bar / 2:.1f}" y="{sy - 4}" text-anchor="middle" fill="{INK}" font-size="9" '
        f'font-family="JetBrains Mono, ui-monospace, monospace">20 km</text></g>'
    )
    legend_y = view.height - 18
    items = [
        (LAND, "Land"),
        (PROTECTED, "Protected area"),
        (GAP, "6 / 12 / 20 kn"),
        (COVERAGE, "Next pass"),
        (TARGET, "Last known"),
    ]
    lx = view.pad_l
    parts.append('<g id="legend">')
    for color, label in items:
        parts.append(f'<rect x="{lx}" y="{legend_y - 8}" width="10" height="10" fill="{color}" stroke="{INK}" stroke-width="0.4"/>')
        parts.append(
            f'<text x="{lx + 14}" y="{legend_y}" fill="{INK}" font-size="9" '
            f'font-family="Inter, system-ui, sans-serif">{escape(label)}</text>'
        )
        lx += 110
    if notes:
        uniq = list(dict.fromkeys(notes))
        parts.append(
            f'<text x="{view.pad_l}" y="{view.height - 6}" fill="{MUTED}" font-size="8" '
            f'font-family="Inter, system-ui, sans-serif">{escape("; ".join(uniq))}</text>'
        )
    parts.append("</g></svg>")
    return "".join(parts)


def map_svg(det_id: str, horizon_h: float) -> str:
    return render_map(build_facts(det_id, horizon_h))


def brief_map_svg(candidates: list[dict]) -> str:
    if not candidates:
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 420"></svg>'
    lats = [float(c["target"]["lat"]) for c in candidates]
    lons = [float(c["target"]["lon"]) for c in candidates]
    lat0 = sum(lats) / len(lats)
    lon0 = sum(lons) / len(lons)
    span = max(max(lats) - min(lats), 0.4) / 2 + 0.35
    view = View(lat0, lon0, half_lat=max(span, 0.45), height=420)
    return _brief_draw(candidates, view)


def _brief_draw(candidates: list[dict], view: View) -> str:
    notes = []
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {view.width} {view.height}" '
        f'width="{view.width}" height="{view.height}" role="img" aria-label="Incident brief map">'
        f"<defs><clipPath id=\"frame\"><rect x=\"{view.pad_l}\" y=\"{view.pad_t}\" width=\"{view.inner_w}\" height=\"{view.inner_h}\"/></clipPath></defs>",
        f'<rect width="{view.width}" height="{view.height}" fill="#fff"/>',
        f'<rect x="{view.pad_l}" y="{view.pad_t}" width="{view.inner_w}" height="{view.inner_h}" fill="{SEA}" stroke="{INK}" stroke-width="0.8"/>',
        '<g clip-path="url(#frame)">',
    ]
    land_fc = load_land()
    if land_fc is None:
        notes.append("reference layer unavailable: land")
    else:
        for item in features_in_bounds(land_fc, view.bounds):
            d = _path(item["geometry"], view)
            if d:
                parts.append(f'<path d="{d}" fill="{LAND}" stroke="{COAST}" stroke-width="0.8"/>')
    countries = load_countries()
    if countries:
        for item in features_in_bounds(countries, view.bounds):
            geom = item["geometry"]
            if geom.is_empty:
                continue
            c = geom.representative_point()
            x, y = view.xy(c.x, c.y)
            name = escape(str(item["properties"].get("name") or ""))
            if name:
                parts.append(
                    f'<text x="{x:.1f}" y="{y:.1f}" fill="{MUTED}" font-size="11" '
                    f'font-family="Inter, system-ui, sans-serif" text-anchor="middle">{name}</text>'
                )
    if load_ports():
        for item in features_in_bounds(load_ports(), view.bounds):
            geom = item["geometry"]
            x, y = view.xy(geom.x, geom.y)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.4" fill="{PORT}"/>')
    for facts in candidates:
        tgt = facts["target"]
        color = {"HIGH": TARGET, "MEDIUM": GAP, "LOW": MUTED}.get((facts.get("priority") or {}).get("tier"), TARGET)
        box = (facts.get("search_area") or {}).get("search_box") or {}
        if box:
            rect = shp_box(box["west"], box["south"], box["east"], box["north"]).intersection(view.clip_window())
            d = _path(rect, view)
            if d:
                parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1"/>')
        x, y = view.xy(tgt["lon"], tgt["lat"])
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}" stroke="{INK}" stroke-width="0.6"/>')
        parts.append(
            f'<text x="{x + 7:.1f}" y="{y - 6:.1f}" fill="{INK}" font-size="10" '
            f'font-family="JetBrains Mono, ui-monospace, monospace">{escape(facts["case"]["id"])}</text>'
        )
    parts.append("</g>")
    nx = view.pad_l + view.inner_w - 18
    ny = view.pad_t + 22
    parts.append(f'<g id="north"><polygon points="{nx},{ny - 12} {nx - 6},{ny + 8} {nx + 6},{ny + 8}" fill="{INK}"/>')
    parts.append(
        f'<text x="{nx}" y="{ny + 20}" text-anchor="middle" fill="{INK}" font-size="9" '
        f'font-family="Inter, system-ui, sans-serif">N</text></g>'
    )
    bar = _scale_km(view, 20)
    sx = view.pad_l + 10
    sy = view.pad_t + view.inner_h - 14
    parts.append(f'<g id="scale"><rect x="{sx}" y="{sy}" width="{bar:.1f}" height="3" fill="{INK}"/>')
    parts.append(
        f'<text x="{sx + bar / 2:.1f}" y="{sy - 4}" text-anchor="middle" fill="{INK}" font-size="9" '
        f'font-family="JetBrains Mono, ui-monospace, monospace">20 km</text></g>'
    )
    if notes:
        parts.append(
            f'<text x="{view.pad_l}" y="{view.height - 8}" fill="{MUTED}" font-size="8" '
            f'font-family="Inter, system-ui, sans-serif">{escape("; ".join(dict.fromkeys(notes)))}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)
