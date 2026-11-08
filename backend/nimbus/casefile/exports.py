"""GPX, KML, GeoJSON, and JSON exports for a patrol crew."""

from __future__ import annotations

import json
from xml.sax.saxutils import escape

from shapely.geometry import mapping

from nimbus.casefile.facts import MARKING, build_facts
from nimbus.casefile.narrative import case_narrative
from nimbus.casefile.reach import SPEED_KN, geodesic_disk, reach_radius_km
from nimbus.geo.reference import clip_to_sea

GPX_NS = "http://www.topografix.com/GPX/1/1"
KML_NS = "http://www.opengis.net/kml/2.2"


def _corners(facts: dict) -> list[dict]:
    box = (facts.get("search_area") or {}).get("search_box") or {}
    order = ("sw", "se", "ne", "nw")
    corners = box.get("corners") or {}
    return [corners[key] for key in order if key in corners]


def render_gpx(facts: dict) -> str:
    case = facts.get("case") or {}
    tgt = facts.get("target") or {}
    det_id = case.get("id") or ""
    acq = case.get("acquisition_time") or ""
    title = f"CASE {det_id} {MARKING}"
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<gpx version="1.1" creator="Nimbus" xmlns="{GPX_NS}">',
        "<metadata>",
        f"<name>{escape(title)}</name>",
        f"<desc>{escape(MARKING)}</desc>",
        f"<time>{escape(acq)}</time>",
        "</metadata>",
        f'<wpt lat="{tgt["lat"]}" lon="{tgt["lon"]}">',
        f"<name>LKP {escape(det_id)}</name>",
        f"<desc>{escape(MARKING)}</desc>",
        f"<time>{escape(acq)}</time>",
        "</wpt>",
    ]
    corners = _corners(facts)
    for pt in corners:
        parts.append(
            f'<wpt lat="{pt["lat"]}" lon="{pt["lon"]}">'
            f"<name>{escape(det_id)} {escape(pt.get('name') or '')}</name>"
            f"<desc>{escape(MARKING)}</desc></wpt>"
        )
    parts.append(f"<rte><name>{escape(det_id)} search box</name><desc>{escape(MARKING)}</desc>")
    ring = corners + corners[:1]
    for pt in ring:
        parts.append(f'<rtept lat="{pt["lat"]}" lon="{pt["lon"]}"><name>{escape(pt.get("name") or "")}</name></rtept>')
    parts.append("</rte></gpx>")
    return "".join(parts)


def _kml_ring(coords: list[tuple[float, float]]) -> str:
    body = " ".join(f"{lon},{lat},0" for lon, lat in coords)
    return f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{body}</coordinates></LinearRing></outerBoundaryIs></Polygon>"


def _disk_coords(lat: float, lon: float, hours: float, kn: float) -> list[tuple[float, float]]:
    disk = geodesic_disk(lat, lon, reach_radius_km(hours, kn))
    clipped, _ = clip_to_sea(disk)
    geom = clipped if not clipped.is_empty else disk
    if geom.geom_type == "MultiPolygon":
        geom = max(geom.geoms, key=lambda g: g.area)
    return [(x, y) for x, y in geom.exterior.coords]


def render_kml(facts: dict) -> str:
    case = facts.get("case") or {}
    tgt = facts.get("target") or {}
    det_id = case.get("id") or ""
    hours = float(((facts.get("search_area") or {}).get("search_box") or {}).get("horizon_h") or case.get("horizon_h") or 3)
    title = f"CASE {det_id} {MARKING}"
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<kml xmlns="{KML_NS}"><Document>',
        f"<name>{escape(title)}</name>",
        f"<description>{escape(MARKING)}</description>",
        "<Style id='lkp'><IconStyle><color>ff4d4fff</color></IconStyle></Style>",
        "<Style id='box'><LineStyle><color>ff000000</color><width>2</width></LineStyle>"
        "<PolyStyle><fill>0</fill></PolyStyle></Style>",
        "<Style id='ring'><LineStyle><color>ff24a5f5</color><width>1.5</width></LineStyle>"
        "<PolyStyle><color>3324a5f5</color></PolyStyle></Style>",
        f"<Placemark><name>LKP {escape(det_id)}</name><description>{escape(MARKING)}</description>"
        f"<styleUrl>#lkp</styleUrl><Point><coordinates>{tgt['lon']},{tgt['lat']},0</coordinates></Point></Placemark>",
    ]
    lat, lon = float(tgt["lat"]), float(tgt["lon"])
    for _key, kn in SPEED_KN.items():
        coords = _disk_coords(lat, lon, hours, kn)
        parts.append(
            f"<Placemark><name>{int(kn)} kn reach</name><description>{escape(MARKING)}</description>"
            f"<styleUrl>#ring</styleUrl>{_kml_ring(coords)}</Placemark>"
        )
    corners = _corners(facts)
    box_coords = [(pt["lon"], pt["lat"]) for pt in corners]
    if box_coords:
        box_coords = box_coords + box_coords[:1]
        parts.append(
            f"<Placemark><name>{escape(det_id)} search box</name><description>{escape(MARKING)}</description>"
            f"<styleUrl>#box</styleUrl>{_kml_ring(box_coords)}</Placemark>"
        )
    ports = facts.get("nearest_ports") or []
    if ports:
        p = ports[0]
        parts.append(
            f"<Placemark><name>{escape(p.get('name') or 'Port')}</name><description>{escape(MARKING)}</description>"
            f"<Point><coordinates>{p['lon']},{p['lat']},0</coordinates></Point></Placemark>"
        )
    parts.append("</Document></kml>")
    return "".join(parts)


def render_geojson(facts: dict) -> dict:
    case = facts.get("case") or {}
    tgt = facts.get("target") or {}
    det_id = case.get("id") or ""
    hours = float(((facts.get("search_area") or {}).get("search_box") or {}).get("horizon_h") or 3)
    lat, lon = float(tgt["lat"]), float(tgt["lon"])
    features = [
        {
            "type": "Feature",
            "properties": {"name": f"LKP {det_id}", "kind": "lkp", "marking": MARKING, "time": case.get("acquisition_time")},
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
        }
    ]
    for _key, kn in SPEED_KN.items():
        disk = geodesic_disk(lat, lon, reach_radius_km(hours, kn))
        clipped, _ = clip_to_sea(disk)
        features.append(
            {
                "type": "Feature",
                "properties": {"name": f"{int(kn)} kn reach", "kind": "reach", "speed_kn": kn, "marking": MARKING},
                "geometry": mapping(clipped if not clipped.is_empty else disk),
            }
        )
    corners = _corners(facts)
    if corners:
        ring = [[pt["lon"], pt["lat"]] for pt in corners]
        ring.append(ring[0])
        features.append(
            {
                "type": "Feature",
                "properties": {"name": f"{det_id} search box", "kind": "search_box", "marking": MARKING},
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        )
        for pt in corners:
            features.append(
                {
                    "type": "Feature",
                    "properties": {"name": f"{det_id} {pt.get('name')}", "kind": "corner", "marking": MARKING},
                    "geometry": {"type": "Point", "coordinates": [pt["lon"], pt["lat"]]},
                }
            )
    ports = facts.get("nearest_ports") or []
    if ports:
        p = ports[0]
        features.append(
            {
                "type": "Feature",
                "properties": {"name": p.get("name"), "kind": "port", "marking": MARKING, "distance_km": p.get("distance_km")},
                "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
            }
        )
    return {"type": "FeatureCollection", "name": f"CASE {det_id} {MARKING}", "features": features}


def render_json(facts: dict, narrative: dict | None = None) -> dict:
    bundle = narrative if narrative is not None else case_narrative(facts)
    return {
        "marking": MARKING,
        "facts": facts,
        "narrative": bundle.get("narrative"),
        "provenance": bundle.get("provenance"),
    }


def export_bytes(det_id: str, fmt: str, horizon_h: float) -> tuple[bytes, str, str]:
    facts = build_facts(det_id, horizon_h)
    case_id = facts["case"]["id"]
    stem = f"{case_id}-UNVERIFIED"
    if fmt == "gpx":
        return render_gpx(facts).encode("utf-8"), "application/gpx+xml", f"{stem}.gpx"
    if fmt == "kml":
        return render_kml(facts).encode("utf-8"), "application/vnd.google-earth.kml+xml", f"{stem}.kml"
    if fmt == "geojson":
        body = json.dumps(render_geojson(facts), ensure_ascii=False).encode("utf-8")
        return body, "application/geo+json", f"{stem}.geojson"
    if fmt == "json":
        body = json.dumps(render_json(facts), ensure_ascii=False, indent=2).encode("utf-8")
        return body, "application/json", f"{stem}.json"
    raise ValueError(f"unsupported export format {fmt}")
