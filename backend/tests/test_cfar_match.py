from datetime import datetime, timedelta, timezone

import numpy as np

from darkwatch.ais import ais_silences, annotate_overlap
from darkwatch.detection import CFARDetector, Fix, confidence_score, interpolate_track, match_detections
from darkwatch.orbit import Gap


def test_cfar_finds_a_bright_cluster_and_ignores_speckle():
    rng = np.random.default_rng(4)
    image = rng.exponential(scale=1.0, size=(80, 80))
    image[40:44, 50:54] = 40.0
    dets = CFARDetector(guard=2, train=6, pfa=1e-6, min_pixels=3, min_peak_db=6).detect(image)
    assert dets, "bright cluster should be detected"
    assert any(abs(d.row - 41.5) < 3 and abs(d.col - 51.5) < 3 for d in dets)
    quiet = rng.exponential(scale=1.0, size=(80, 80))
    false = CFARDetector(guard=2, train=6, pfa=1e-8, min_pixels=4, min_peak_db=8).detect(quiet)
    assert len(false) <= 2


def test_cfar_respects_a_land_mask():
    image = np.ones((40, 40))
    image[10:14, 10:14] = 80
    valid = np.ones((40, 40), dtype=bool)
    valid[8:16, 8:16] = False
    dets = CFARDetector(guard=1, train=4, pfa=1e-6, min_pixels=2, min_peak_db=3).detect(image, valid=valid)
    assert dets == []


def test_interpolate_and_match():
    t0 = datetime(2026, 11, 2, 5, 20, tzinfo=timezone.utc)
    when = datetime(2026, 11, 2, 5, 23, 46, tzinfo=timezone.utc)
    tracks = {
        "219000111": [
            Fix("219000111", t0, 56.90, 11.80, "NORDEN"),
            Fix("219000111", t0 + timedelta(minutes=8), 56.92, 11.84, "NORDEN"),
        ],
        "219000222": [
            Fix("219000222", t0, 57.40, 12.40, "FAR"),
            Fix("219000222", t0 + timedelta(minutes=8), 57.41, 12.41, "FAR"),
        ],
    }
    pos = interpolate_track(tracks["219000111"], when, max_gap_s=600)
    assert pos is not None
    assert 56.90 < pos.lat < 56.92
    dets = [
        {"id": "d1", "lat": pos.lat, "lon": pos.lon + 0.01, "peak_db": 11, "pixels": 5},
        {"id": "d2", "lat": 56.2, "lon": 11.2, "peak_db": 9, "pixels": 4},
    ]
    matched = match_detections(dets, tracks, when, max_km=3.0, max_gap_s=600)
    by_id = {row["id"]: row for row in matched}
    assert by_id["d1"]["matched"] is True
    assert by_id["d1"]["mmsi"] == "219000111"
    assert by_id["d2"]["matched"] is False
    assert by_id["d2"]["nearest_ais_km"] > 3


def test_long_ais_gap_is_not_interpolated():
    t0 = datetime(2026, 11, 2, 4, 0, tzinfo=timezone.utc)
    fixes = [
        Fix("1", t0, 56.0, 11.0, "A"),
        Fix("1", t0 + timedelta(hours=2), 56.2, 11.2, "A"),
    ]
    when = t0 + timedelta(hours=1)
    assert interpolate_track(fixes, when, max_gap_s=600) is None


def test_silence_overlap_uses_computed_gaps():
    t0 = datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc)
    tracks = {
        "219": [
            Fix("219", t0 + timedelta(hours=1), 56.9, 11.8, "QUIET"),
            Fix("219", t0 + timedelta(hours=5), 56.91, 11.82, "QUIET"),
        ]
    }
    bbox = (11.4, 56.5, 12.4, 57.3)
    sil = ais_silences(tracks, bbox, min_gap_s=1800)
    assert len(sil) == 1
    assert sil[0]["duration_s"] == 4 * 3600
    gap = Gap(t0 + timedelta(hours=2), t0 + timedelta(hours=4), 2 * 3600)
    ann = annotate_overlap(sil, [gap])
    assert ann[0]["overlaps_coverage_gap"] is True
    assert ann[0]["overlap_gap_s"] == 2 * 3600
    assert ann[0]["coverage_gap"]["duration_s"] == 2 * 3600


def test_confidence_is_bounded():
    assert 0 <= confidence_score(14, 20, 6, 15) <= 1
