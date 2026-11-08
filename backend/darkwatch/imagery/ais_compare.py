"""AIS comparison for a GeoTIFF footprint. Never fabricates a match."""

from __future__ import annotations

from datetime import timedelta, timezone

from darkwatch.ais.ais_io import load_tracks
from darkwatch.detection.matching import interpolate_track, match_detections
from darkwatch.orbit import parse_time

MAX_GAP_S = 600.0
PAD_DEG = 0.2
MATCH_KM = 3.0


def _in_bbox(lat: float, lon: float, bbox: list[float], pad: float = 0.0) -> bool:
    west, south, east, north = bbox
    return south - pad <= lat <= north + pad and west - pad <= lon <= east + pad


def compare(detections: list[dict], bbox: list[float], when_iso: str) -> dict:
    when = parse_time(when_iso)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    t0 = when - timedelta(minutes=10)
    t1 = when + timedelta(minutes=10)
    tracks = load_tracks()
    scene = {}
    n_pings = 0
    for mmsi, fixes in tracks.items():
        kept = []
        for fix in fixes:
            ts = fix.t if fix.t.tzinfo else fix.t.replace(tzinfo=timezone.utc)
            if t0 <= ts <= t1 and _in_bbox(fix.lat, fix.lon, bbox, PAD_DEG):
                kept.append(fix)
                n_pings += 1
        if kept:
            scene[mmsi] = fixes
    if n_pings == 0:
        return {
            "available": False,
            "reason": "No AIS data for this area and time in the loaded store",
        }
    positioned = []
    for fixes in scene.values():
        pos = interpolate_track(fixes, when, MAX_GAP_S)
        if pos is not None and _in_bbox(pos.lat, pos.lon, bbox):
            positioned.append(pos)
    vessel = [d for d in detections if d["status"] == "vessel_like" and d.get("lat") is not None]
    matched_rows = match_detections(vessel, scene, when, max_km=MATCH_KM, max_gap_s=MAX_GAP_S)
    by_id = {row["id"]: row for row in matched_rows}
    matched_mmsis = set()
    n_matched = 0
    n_dark = 0
    for det in detections:
        row = by_id.get(det["id"])
        if det["status"] != "vessel_like":
            continue
        if row and row.get("matched"):
            det["ais"] = {
                "status": "matched",
                "name": row.get("name"),
                "mmsi": row.get("mmsi"),
                "match_km": row.get("match_km"),
            }
            matched_mmsis.add(str(row.get("mmsi")))
            n_matched += 1
        else:
            det["ais"] = {"status": "dark_candidate", "name": None, "mmsi": None, "match_km": None}
            n_dark += 1
    ais_only = []
    for pos in positioned:
        if pos.mmsi in matched_mmsis:
            continue
        ais_only.append(
            {
                "mmsi": pos.mmsi,
                "name": pos.name,
                "lat": pos.lat,
                "lon": pos.lon,
                "sog": pos.sog,
            }
        )
    return {
        "available": True,
        "matched": n_matched,
        "dark_candidates": n_dark,
        "ais_only": ais_only,
        "n_interpolated": len(positioned),
        "n_pings": n_pings,
    }
