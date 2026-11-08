"""Match SAR detections to public AIS by interpolating tracks to acquisition time."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from nimbus.orbit.geometry import haversine_km


@dataclass
class Fix:
    mmsi: str
    t: datetime
    lat: float
    lon: float
    name: str = ""
    sog: float | None = None


@dataclass
class Interp:
    mmsi: str
    name: str
    lat: float
    lon: float
    gap_s: float
    sog: float | None = None
    cog: float | None = None
    t0: datetime | None = None
    t1: datetime | None = None


def interpolate_track(fixes: list[Fix], when: datetime, max_gap_s: float) -> Interp | None:
    """Linear lat/lon interpolation. Rejects a bracket longer than max_gap_s."""
    if len(fixes) < 2:
        return None
    fixes = sorted(fixes, key=lambda f: f.t)
    if when < fixes[0].t or when > fixes[-1].t:
        # Allow a single-sided snap only when a ping is very close in time.
        nearest = min(fixes, key=lambda f: abs((f.t - when).total_seconds()))
        dt = abs((nearest.t - when).total_seconds())
        if dt <= min(60.0, max_gap_s):
            return Interp(
                nearest.mmsi,
                nearest.name,
                nearest.lat,
                nearest.lon,
                dt,
                sog=nearest.sog,
                t0=nearest.t,
                t1=nearest.t,
            )
        return None
    lo, hi = 0, len(fixes) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if fixes[mid].t <= when:
            lo = mid
        else:
            hi = mid
    a, b = fixes[lo], fixes[hi]
    span = (b.t - a.t).total_seconds()
    if span <= 0 or span > max_gap_s:
        return None
    frac = (when - a.t).total_seconds() / span
    sog = None
    if a.sog is not None and b.sog is not None:
        sog = a.sog + frac * (b.sog - a.sog)
    elif a.sog is not None:
        sog = a.sog
    elif b.sog is not None:
        sog = b.sog
    return Interp(
        mmsi=a.mmsi,
        name=a.name or b.name,
        lat=a.lat + frac * (b.lat - a.lat),
        lon=a.lon + frac * (b.lon - a.lon),
        gap_s=span,
        sog=sog,
        t0=a.t,
        t1=b.t,
    )


def match_detections(
    detections: list[dict],
    tracks: dict[str, list[Fix]],
    when: datetime,
    max_km: float = 3.0,
    max_gap_s: float = 600.0,
) -> list[dict]:
    """Greedy one-to-one match. Unmatched detections stay unmatched.

    `nearest_ais_km` is filled even when it exceeds max_km, so the UI can say
    how far the closest public AIS position was.
    """
    positioned: list[Interp] = []
    for fixes in tracks.values():
        pos = interpolate_track(fixes, when, max_gap_s=max_gap_s)
        if pos is not None:
            positioned.append(pos)

    pairs: list[tuple[float, int, int]] = []
    nearest = [(None, None) for _ in detections]  # km, index
    for di, det in enumerate(detections):
        best = None
        best_i = None
        for pi, pos in enumerate(positioned):
            dist = haversine_km(det["lat"], det["lon"], pos.lat, pos.lon)
            if best is None or dist < best:
                best = dist
                best_i = pi
            if dist <= max_km:
                pairs.append((dist, di, pi))
        nearest[di] = (best, best_i)
    pairs.sort()
    used_d: set[int] = set()
    used_p: set[int] = set()
    assigned: dict[int, tuple[float, Interp]] = {}
    for dist, di, pi in pairs:
        if di in used_d or pi in used_p:
            continue
        used_d.add(di)
        used_p.add(pi)
        assigned[di] = (dist, positioned[pi])

    results = []
    for di, det in enumerate(detections):
        row = dict(det)
        near_km, near_i = nearest[di]
        row["nearest_ais_km"] = None if near_km is None else round(near_km, 2)
        row["nearest_mmsi"] = None if near_i is None else positioned[near_i].mmsi
        row["nearest_name"] = None if near_i is None else positioned[near_i].name
        if di in assigned:
            dist, pos = assigned[di]
            row["matched"] = True
            row["mmsi"] = pos.mmsi
            row["name"] = pos.name
            row["match_km"] = round(dist, 2)
            row["ais_lat"] = pos.lat
            row["ais_lon"] = pos.lon
        else:
            row["matched"] = False
            row["mmsi"] = None
            row["name"] = None
            row["match_km"] = None
            row["ais_lat"] = None
            row["ais_lon"] = None
        results.append(row)
    return results


def confidence_score(peak_db: float, shore_km: float, pixels: int, nearest_ais_km: float | None) -> float:
    """Relative score for an unmatched detection. Not a probability of wrongdoing."""
    strength = max(0.0, min(1.0, (peak_db - 6.0) / 12.0))
    size = max(0.0, min(1.0, pixels / 8.0))
    offshore = max(0.0, min(1.0, shore_km / 12.0))
    isolated = 0.0
    if nearest_ais_km is None:
        isolated = 1.0
    elif nearest_ais_km > 8:
        isolated = min(1.0, (nearest_ais_km - 8.0) / 20.0)
    score = 0.5 * strength + 0.2 * size + 0.2 * offshore + 0.1 * isolated
    return round(max(0.0, min(1.0, score)), 3)
