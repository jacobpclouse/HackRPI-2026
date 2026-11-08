"""48-hour reacquisition plan for a Kattegat dark candidate."""

from __future__ import annotations

import threading
from datetime import timedelta

from shapely.geometry import shape as shp_shape

from nimbus.casefile.candidates import acquisition_time, require_dark_candidate
from nimbus.casefile.reach import (
    SPEED_KN,
    clip_to_sea,
    coverage_fraction,
    geodesic_disk,
    land_available,
    reach_radius_km,
)
from nimbus.catalog import get_catalog
from nimbus.orbit.orbit import ensure_utc, parse_time
from nimbus.orbit.passes import abeam_passes, spec_of, swath_polygon, swath_reaches

HORIZON_H = 48.0
MIN_HOURS = 0.15

_cache: dict[str, dict] = {}
_lock = threading.Lock()


def _iso(dt) -> str:
    dt = ensure_utc(dt)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _assumptions(clipped: bool) -> list[str]:
    out = [
        "Slow 6 kn, typical 12 kn, and fast 20 kn are constant-speed assumptions, not tracks.",
        "Reach areas assume constant speed and ignore routing.",
        "A swath overflight is not proof an image was acquired.",
        "Tasked fleets are possible coverage and require tasking.",
    ]
    if clipped:
        out.append("Reach disks are clipped to sea using the packaged Natural Earth land mask.")
    else:
        out.append("Reach disks are not clipped to coastline.")
    return out


def _pick_best(passes: list[dict]) -> dict | None:
    systematic = [p for p in passes if p["coverage"] == "systematic"]
    qualified = [p for p in systematic if p["coverage_frac"].get("typical", 0) >= 0.5]
    if qualified:
        return min(qualified, key=lambda p: p["center"])
    covered = [p for p in passes if any(v > 0 for v in p["coverage_frac"].values())]
    if not covered:
        return None
    return min(covered, key=lambda p: p["center"])


def build_plan(det_id: str) -> dict:
    row = require_dark_candidate(det_id)
    t_acq = acquisition_time()
    t1 = t_acq + timedelta(hours=HORIZON_H)
    lat, lon = float(row["lat"]), float(row["lon"])
    cat = get_catalog()
    clipped = land_available()
    passes_out: list[dict] = []
    for rec in cat.satellites:
        spec = spec_of(rec)
        hits: list[dict] = []
        for p in abeam_passes(rec, lat, lon, t_acq, t1):
            hours = (ensure_utc(p.center) - t_acq).total_seconds() / 3600.0
            if hours < MIN_HOURS or hours > HORIZON_H:
                continue
            r_typ = reach_radius_km(hours, SPEED_KN["typical"])
            if not swath_reaches(p.cross_km, p.alt_km, spec, r_typ):
                continue
            feat = swath_polygon(rec, p.center)
            if not feat.get("geometry"):
                continue
            swath = shp_shape(feat["geometry"])
            typical, _ = clip_to_sea(geodesic_disk(lat, lon, r_typ))
            if typical.is_empty or not swath.intersects(typical):
                continue
            fracs = {}
            for name, kn in SPEED_KN.items():
                disk, _ = clip_to_sea(geodesic_disk(lat, lon, reach_radius_km(hours, kn)))
                fracs[name] = round(coverage_fraction(swath, disk, lat, lon), 4)
            tasked = p.coverage == "possible"
            hits.append(
                {
                    "norad": p.norad,
                    "name": p.name,
                    "family": p.family,
                    "coverage": "tasked" if tasked else "systematic",
                    "label": "possible, requires tasking" if tasked else "systematic swath",
                    "start": _iso(p.start),
                    "end": _iso(p.end),
                    "center": _iso(p.center),
                    "hours_after": round(hours, 2),
                    "coverage_frac": fracs,
                    "archive": None,
                    "color": p.color,
                }
            )
        hits.sort(key=lambda item: item["center"])
        merged: list[dict] = []
        for item in hits:
            if merged and abs((parse_time(item["center"]) - parse_time(merged[-1]["center"])).total_seconds()) < 240:
                continue
            merged.append(item)
        passes_out.extend(merged)
    passes_out.sort(key=lambda item: (0 if item["coverage"] == "systematic" else 1, item["center"]))
    best = _pick_best(passes_out)
    if best:
        for item in passes_out:
            item["best"] = item is best or (
                item["norad"] == best["norad"] and item["center"] == best["center"]
            )
    else:
        for item in passes_out:
            item["best"] = False
    return {
        "detection": {
            "id": row["id"],
            "lat": lat,
            "lon": lon,
        },
        "t_acq": _iso(t_acq),
        "horizon_h": HORIZON_H,
        "speeds_kn": SPEED_KN,
        "passes": passes_out,
        "best_next": best,
        "clipped_to_coastline": clipped,
        "assumptions": _assumptions(clipped),
    }


def plan_for(det_id: str) -> dict:
    with _lock:
        cached = _cache.get(det_id)
    if cached is not None:
        return cached
    plan = build_plan(det_id)
    with _lock:
        _cache[det_id] = plan
    return plan


def clear_plan_cache() -> None:
    with _lock:
        _cache.clear()
