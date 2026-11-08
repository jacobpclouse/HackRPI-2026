"""Kattegat AIS-only: interpolated AIS at acquisition with no radar match.

Uses the same track window and ``interpolate_track`` as prepare/matching
(scene bbox + 0.2°, max gap 600 s). That population is
``summary.ais_interpolated_for_match`` (94); AIS-only is 94 − 18 = 76.
"""

from __future__ import annotations

import json
from datetime import datetime

from darkwatch import paths
from darkwatch.ais.ais_io import load_tracks
from darkwatch.detection.matching import interpolate_track
from darkwatch.orbit.orbit import parse_time
from darkwatch.storage import get_snapshot

NOTE = (
    "Broadcasting AIS at the time of the pass; not detected by radar "
    "(usually small vessels, near shore, or in masked areas)"
)
PAD_DEG = 0.2
MAX_GAP_S = 600.0


def _iso(when: datetime | None) -> str | None:
    if when is None:
        return None
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _summary_and_bbox() -> tuple[dict, list[float]]:
    snap = get_snapshot()
    summary = snap.summary or {}
    if summary.get("bbox"):
        return summary, list(summary["bbox"])
    meta = snap.meta or json.loads((paths.demo_dir() / "scene_meta.json").read_text())
    return summary, list(meta["bbox"])


def interpolated_scene_tracks(when: datetime, bbox: list[float]) -> list:
    west, south, east, north = bbox
    tracks = load_tracks()
    scene = {}
    for mmsi, fixes in tracks.items():
        if any(south - PAD_DEG <= f.lat <= north + PAD_DEG and west - PAD_DEG <= f.lon <= east + PAD_DEG for f in fixes):
            scene[mmsi] = fixes
    out = []
    for fixes in scene.values():
        pos = interpolate_track(fixes, when, MAX_GAP_S)
        if pos is not None:
            out.append(pos)
    return out


def ais_only_vessels() -> list[dict]:
    summary, bbox = _summary_and_bbox()
    when = parse_time(summary["scene_time"])
    positioned = interpolated_scene_tracks(when, bbox)
    snap = get_snapshot()
    matched_mmsis = {str(row["mmsi"]) for row in (snap.matches or []) if row.get("matched") and row.get("mmsi")}
    only = [pos for pos in positioned if pos.mmsi not in matched_mmsis]
    expected = None
    if summary.get("ais_interpolated_for_match") is not None and summary.get("matched") is not None:
        expected = int(summary["ais_interpolated_for_match"]) - int(summary["matched"])
    if expected is not None and len(only) != expected:
        raise RuntimeError(
            f"AIS-only count {len(only)} != interpolated {summary.get('ais_interpolated_for_match')} "
            f"− matched {summary.get('matched')} ({expected}). "
            "Not adjusting numbers; matching and interpolation must stay in lockstep."
        )
    rows = []
    for pos in only:
        rows.append(
            {
                "mmsi": pos.mmsi,
                "name": pos.name,
                "lat": pos.lat,
                "lon": pos.lon,
                "sog": None if pos.sog is None else round(float(pos.sog), 1),
                "cog": pos.cog,
                "interpolated_from": [_iso(pos.t0), _iso(pos.t1)],
                "note": NOTE,
            }
        )
    return rows


def ais_only_geojson() -> dict:
    rows = ais_only_vessels()
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {k: v for k, v in row.items() if k not in ("lat", "lon")},
                "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
            }
            for row in rows
        ],
    }
