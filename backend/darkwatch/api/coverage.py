"""/api/coverage and /api/story."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query

from darkwatch.ais import ais_silences, annotate_overlap, load_tracks, onset_after_pass
from darkwatch.api.common import split_families
from darkwatch.catalog import SYSTEMATIC_FAMILIES
from darkwatch.detection import coverage_report, floor_now, sentinel_validation
from darkwatch.orbit import Gap, parse_time
from darkwatch.services.evidence import review_block
from darkwatch.storage import get_snapshot, ping_tracks, report_from_stored

router = APIRouter()

BASELINE_WINDOW_MIN = 30


@router.get("/api/coverage")
def coverage(
    lat: float | None = Query(None),
    lon: float | None = Query(None),
    hours: float = 48,
    start: str | None = None,
    families: str | None = None,
):
    if lat is None or lon is None:
        raise HTTPException(400, "lat and lon are required query parameters, in decimal degrees")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(400, "lat/lon out of range")
    if hours <= 0 or hours > 96:
        raise HTTPException(400, "hours must be between 0 and 96")
    t0 = parse_time(start) if start else None
    try:
        return coverage_report(lat, lon, t0, hours, split_families(families))
    except Exception as exc:
        raise HTTPException(503, f"Pass prediction failed: {exc}") from exc


def _gap_objects(report: dict) -> list[Gap]:
    out = []
    for gap in report["gaps"]:
        out.append(
            Gap(
                start=parse_time(gap["start"]),
                end=parse_time(gap["end"]),
                duration_s=gap["duration_s"],
            )
        )
    return out


def _gap_passes(report: dict) -> list[dict]:
    """The systematic passes that decide the report's gaps."""
    fams = set(report.get("gap_families") or SYSTEMATIC_FAMILIES)
    return [p for p in report["passes"] if p["coverage"] == "systematic" and p["family"] in fams]


@router.get("/api/story")
def story(families: str | None = None):
    """Scene-day gaps, AIS silences, and the next 48 hours for the Kattegat chip."""
    snap = get_snapshot()
    summary = snap.summary
    meta = snap.meta
    if not summary or not meta:
        raise HTTPException(404, "Scene sample is missing. Run make prepare.")
    west, south, east, north = meta["bbox"]
    lat = (south + north) / 2
    lon = (west + east) / 2
    scene_time = parse_time(summary["scene_time"])
    day0 = scene_time.replace(hour=0, minute=0, second=0, microsecond=0)
    day1 = day0 + timedelta(hours=24)
    gap_families = split_families(families)
    day = report_from_stored(snap.passes, "scene_day", day0, day1, gap_families)
    if day is None:
        day = coverage_report(lat, lon, day0, 24, gap_families)
    upcoming_start = floor_now()
    upcoming = None
    try:
        upcoming = coverage_report(lat, lon, upcoming_start, 48, gap_families)
    except Exception:
        upcoming = report_from_stored(
            snap.passes, "upcoming", upcoming_start, upcoming_start + timedelta(hours=48), gap_families
        )
    if upcoming is None:
        raise HTTPException(503, "Pass prediction failed and no stored passes are available.")
    validation = sentinel_validation(day, scene_time)
    tracks = ping_tracks(snap.pings) if snap.pings is not None else load_tracks()
    silences = ais_silences(tracks, tuple(meta["bbox"]), min_gap_s=1800)
    annotated = annotate_overlap(silences, _gap_objects(day))
    overlapping = [row for row in annotated if row["overlaps_coverage_gap"]]
    baseline = onset_after_pass(silences, _gap_passes(day), BASELINE_WINDOW_MIN, day0, day1)
    baseline["meaning"] = (
        f"Fraction of AIS silences that start within {BASELINE_WINDOW_MIN} minutes after a systematic "
        "pass ends, against the fraction of the day those post-pass windows cover. "
        "If p_value is above 0.05, this sample does not show timing beyond chance."
    )
    return {
        "summary": summary,
        "meta": {
            "scene_id": meta["scene_id"],
            "datetime": meta["datetime"],
            "platform": meta.get("platform"),
            "orbit_state": meta.get("orbit_state"),
            "bbox": meta["bbox"],
        },
        "observed_acquisition": {
            "time": summary["scene_time"],
            "scene_id": summary["scene_id"],
            "platform": meta.get("platform"),
            "source": "Planetary Computer STAC timestamp, not an SGP4 estimate",
        },
        "validation": validation,
        "scene_day": day,
        "upcoming": upcoming,
        "ais_silences": annotated[:25],
        "ais_silence_count": len(annotated),
        "silences_overlapping_gap": len(overlapping),
        "intent_baseline": baseline,
        "ethics": summary.get("note"),
        "data_source": snap.source,
        "refreshed_at": snap.refreshed_at,
        "review": review_block(snap.matches or []),
    }
