"""Coverage reports. Gap lengths are derived from pass windows every time."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from nimbus.catalog import SYSTEMATIC_FAMILIES, get_catalog
from nimbus.orbit.gaps import coverage_gaps, longest_gap
from nimbus.orbit.orbit import parse_time
from nimbus.orbit.passes import predict_passes

_cache: dict[tuple, dict] = {}
_lock = threading.Lock()


def floor_now(minutes: int = 10) -> datetime:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    return now.replace(minute=(now.minute // minutes) * minutes)


def coverage_report(
    lat: float,
    lon: float,
    start: datetime | None = None,
    hours: float = 48,
    gap_families: list[str] | None = None,
) -> dict:
    t0 = start or floor_now()
    if t0.tzinfo is None:
        t0 = t0.replace(tzinfo=timezone.utc)
    families = list(gap_families or SYSTEMATIC_FAMILIES)
    key = (
        round(lat, 3),
        round(lon, 3),
        t0.strftime("%Y-%m-%dT%H:%M"),
        round(hours, 2),
        tuple(families),
    )
    with _lock:
        cached = _cache.get(key)
    if cached:
        return cached
    cat = get_catalog()
    t1 = t0 + timedelta(hours=hours)
    passes = predict_passes(cat.satellites, lat, lon, t0, t1)
    family_set = set(families)
    systematic = [p for p in passes if p.coverage == "systematic" and p.family in family_set]
    possible = [p for p in passes if p.coverage == "possible"]
    gaps = coverage_gaps(systematic, t0, t1)
    long = longest_gap(gaps)
    # Optimistic hole if every tasked access were actually imaged.
    optimistic = coverage_gaps(passes, t0, t1)
    opt_long = longest_gap(optimistic)
    epochs = sorted({s.epoch for s in cat.satellites})
    report = {
        "lat": lat,
        "lon": lon,
        "start": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": t1.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hours": hours,
        "gp_fetched_at": cat.fetched_at,
        "epoch_min": epochs[0] if epochs else None,
        "epoch_max": epochs[-1] if epochs else None,
        "satellite_count": len(cat.satellites),
        "gap_families": families,
        "systematic_pass_count": len(systematic),
        "possible_pass_count": len(possible),
        "passes": [p.to_dict() for p in passes],
        "gaps": [g.to_dict() for g in gaps],
        "longest_gap": long.to_dict() if long else None,
        "longest_gap_if_all_tasked": opt_long.to_dict() if opt_long else None,
        "note": (
            "Gaps count only systematic-mission swath geometry "
            "(Sentinel-1, RCM, NISAR, ALOS-2/4, SAOCOM) unless gap_families is narrowed. "
            "A swath overflight is not proof an image was acquired. "
            "Tasked fleets are possible coverage and do not close a gap."
        ),
    }
    with _lock:
        _cache[key] = report
    return report


def sentinel_validation(report: dict, scene_time: datetime) -> dict:
    """How close a predicted Sentinel-1 pass is to the real acquisition."""
    best = None
    best_abs = None
    for p in report["passes"]:
        if p["family"] != "Sentinel-1":
            continue
        center = parse_time(p["center"])
        delta = (center - scene_time).total_seconds()
        if best_abs is None or abs(delta) < best_abs:
            best_abs = abs(delta)
            best = {"pass": p, "offset_s": round(delta, 1)}
    if best is None:
        quality = "none"
    elif best_abs <= 600:
        quality = "good"
    elif best_abs <= 1800:
        quality = "fair"
    else:
        quality = "poor"
    return {
        "quality": quality,
        "nearest": best,
        "meaning": (
            "Predicted Sentinel-1 time versus the Planetary Computer acquisition timestamp. "
            "SGP4 is propagated from the public GP epoch, which may be days from the scene."
        ),
    }
