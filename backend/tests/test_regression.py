"""Packaged-demo numbers that the README and the pitch quote.

Re-runs AIS matching and pass prediction on the committed data, so a change
to the science (or an import that silently swaps a function) fails here.
"""

import json
from datetime import datetime, timedelta, timezone

from nimbus import paths
from nimbus.ais import load_tracks
from nimbus.catalog import SYSTEMATIC_FAMILIES, read, snapshot_path
from nimbus.detection import match_detections
from nimbus.orbit import coverage_gaps, longest_gap, predict_passes

DEMO = paths.demo_dir()
SCENE_TIME = datetime(2026, 11, 2, 5, 23, 46, tzinfo=timezone.utc)


def _bbox():
    return json.loads((DEMO / "scene_meta.json").read_text())["bbox"]


def test_matching_reproduces_21_18_3():
    west, south, east, north = _bbox()
    dets = json.loads((DEMO / "detections_raw.json").read_text())
    tracks = load_tracks(DEMO / "ais_pings.csv.gz")
    scene_tracks = {
        mmsi: fixes
        for mmsi, fixes in tracks.items()
        if any(south - 0.2 <= f.lat <= north + 0.2 and west - 0.2 <= f.lon <= east + 0.2 for f in fixes)
    }
    rows = match_detections(dets, scene_tracks, SCENE_TIME, max_km=3.0, max_gap_s=600)
    assert len(rows) == 21
    assert sum(1 for r in rows if r["matched"]) == 18
    assert sorted(r["id"] for r in rows if not r["matched"]) == ["D002", "D016", "D021"]
    summary = json.loads((DEMO / "summary.json").read_text())
    assert (summary["detections"], summary["matched"], summary["unmatched"]) == (21, 18, 3)


def test_sentinel_1d_pass_and_scene_day_gap():
    west, south, east, north = _bbox()
    lat, lon = (south + north) / 2, (west + east) / 2
    cat = read(snapshot_path(), origin="snapshot")
    day0 = SCENE_TIME.replace(hour=0, minute=0, second=0)
    passes = predict_passes(cat.satellites, lat, lon, day0, day0 + timedelta(hours=24))
    s1d = [p for p in passes if p.name == "SENTINEL-1D"]
    assert s1d, "Sentinel-1D should pass over the Kattegat chip on 2 Nov 2026"
    offset = min(abs((p.center - SCENE_TIME).total_seconds()) for p in s1d)
    assert offset <= 3.0
    systematic = [p for p in passes if p.coverage == "systematic" and p.family in SYSTEMATIC_FAMILIES]
    gap = longest_gap(coverage_gaps(systematic, day0, day0 + timedelta(hours=24)))
    assert gap is not None
    assert round(gap.duration_s / 3600, 1) == 6.1
    assert gap.start.strftime("%H:%M") == "05:40"
    assert gap.end.strftime("%H:%M") == "11:46"
