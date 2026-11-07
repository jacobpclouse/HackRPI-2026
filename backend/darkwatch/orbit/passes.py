"""Predict when a ground point sits inside an approximate SAR swath."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import numpy as np

# Only the leaf module: darkwatch.catalog imports this package while it loads.
from darkwatch.catalog.families import FamilySpec
from darkwatch.orbit.geometry import (
    along_cross_km_many,
    destination,
    ground_range_km,
    headings_deg,
)
from darkwatch.orbit.orbit import propagate_many, satrec_from_omm

if TYPE_CHECKING:
    from darkwatch.catalog.records import SatRecord


def satrec_for(rec: SatRecord):
    return satrec_from_omm(rec.omm)


@dataclass
class Pass:
    norad: int
    name: str
    family: str
    coverage: str
    start: datetime
    end: datetime
    center: datetime
    cross_km: float
    alt_km: float
    color: str

    def to_dict(self) -> dict:
        return {
            "norad": self.norad,
            "name": self.name,
            "family": self.family,
            "coverage": self.coverage,
            "label": "possible coverage" if self.coverage == "possible" else "systematic swath",
            "start": _iso(self.start),
            "end": _iso(self.end),
            "center": _iso(self.center),
            "cross_km": round(self.cross_km, 1),
            "alt_km": round(self.alt_km, 1),
            "color": self.color,
        }


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def spec_of(rec: SatRecord) -> FamilySpec:
    return FamilySpec(
        family=rec.family,
        coverage=rec.coverage,
        look=rec.look,
        inc_near=rec.inc_near,
        inc_far=rec.inc_far,
        access_inc=rec.access_inc,
        nominal_width_km=rec.nominal_width_km,
        color=rec.color,
        note=rec.note,
    )


def in_swath(cross_km: float, alt_km: float, spec: FamilySpec) -> bool:
    """True when the point is inside the mission's coverage model at abeam."""
    if not np.isfinite(cross_km) or not np.isfinite(alt_km):
        return False
    if spec.coverage == "possible":
        near = ground_range_km(alt_km, 15.0)
        far = ground_range_km(alt_km, spec.access_inc)
        if not np.isfinite(near) or not np.isfinite(far):
            return False
        if spec.look == "either":
            return near <= abs(cross_km) <= far
        return near <= cross_km <= far
    near = ground_range_km(alt_km, spec.inc_near)
    far = ground_range_km(alt_km, spec.inc_far)
    if not np.isfinite(near) or not np.isfinite(far):
        return False
    if spec.look == "left":
        return -far <= cross_km <= -near
    if spec.look == "either":
        return near <= abs(cross_km) <= far
    return near <= cross_km <= far


def display_ranges_km(alt_km: float, spec: FamilySpec) -> tuple[float, float]:
    """Near and far ground range of the strip drawn on the globe."""
    if spec.nominal_width_km:
        center_inc = 32.0
        center = ground_range_km(alt_km, center_inc)
        half = spec.nominal_width_km / 2.0
        if not np.isfinite(center):
            return float("nan"), float("nan")
        return max(20.0, center - half), center + half
    return ground_range_km(alt_km, spec.inc_near), ground_range_km(alt_km, spec.inc_far)


def find_passes(
    rec: SatRecord,
    lat: float,
    lon: float,
    t0: datetime,
    t1: datetime,
    step_s: int = 30,
) -> list[Pass]:
    spec = spec_of(rec)
    span = (t1 - t0).total_seconds()
    if span <= 0:
        return []
    n = int(span // step_s) + 1
    times = [t0 + timedelta(seconds=i * step_s) for i in range(n)]
    sat = satrec_for(rec)
    pos = propagate_many(sat, times)
    lats, lons, alts = pos["lat"], pos["lon"], pos["alt_km"]
    heads = headings_deg(lats, lons)
    along, cross = along_cross_km_many(lats, lons, heads, lat, lon)
    finite = np.isfinite(along[:-1]) & np.isfinite(along[1:]) & np.isfinite(cross[:-1])
    close = (np.abs(along[:-1]) < 2200) & (np.abs(along[1:]) < 2200)
    sign = along[:-1] * along[1:] < 0
    hits = np.where(finite & close & sign)[0]
    found: list[Pass] = []
    for i in hits:
        denom = abs(along[i]) + abs(along[i + 1])
        frac = 0.0 if denom == 0 else abs(float(along[i])) / denom
        cross_i = float(cross[i] + frac * (cross[i + 1] - cross[i]))
        alt_i = float(alts[i] + frac * (alts[i + 1] - alts[i]))
        if not in_swath(cross_i, alt_i, spec):
            continue
        center = times[i] + timedelta(seconds=step_s * frac)
        half = timedelta(seconds=25)
        found.append(
            Pass(
                norad=rec.norad,
                name=rec.name,
                family=rec.family,
                coverage=rec.coverage,
                start=center - half,
                end=center + half,
                center=center,
                cross_km=cross_i,
                alt_km=alt_i,
                color=rec.color,
            )
        )
    found.sort(key=lambda p: p.center)
    merged: list[Pass] = []
    for p in found:
        if merged and (p.center - merged[-1].center) < timedelta(minutes=4):
            continue
        merged.append(p)
    return merged


def predict_passes(
    records: list[SatRecord],
    lat: float,
    lon: float,
    t0: datetime,
    t1: datetime,
    families: set[str] | None = None,
    coverage: str | None = None,
) -> list[Pass]:
    out: list[Pass] = []
    for rec in records:
        if families is not None and rec.family not in families:
            continue
        if coverage is not None and rec.coverage != coverage:
            continue
        out.extend(find_passes(rec, lat, lon, t0, t1))
    out.sort(key=lambda p: p.start)
    return out


def next_pass_over_polygon(
    polygon: dict,
    t0: datetime,
    horizon_h: float,
    families: set[str] | None = None,
) -> list[Pass]:
    """Next swath passes that cover any part of a GeoJSON polygon.

    Reserved for the "Catch it" feature: given a vessel's possible-position
    area, return the soonest passes (systematic first, then possible) within
    ``horizon_h`` hours of ``t0``, optionally limited to ``families``.
    """
    raise NotImplementedError("next_pass_over_polygon is reserved for the Catch it feature")


def swath_polygon(rec: SatRecord, when: datetime, half_s: int = 100, step_s: int = 8) -> dict:
    """GeoJSON polygon for the approximate radar strip around `when`."""
    spec = spec_of(rec)
    times = [when + timedelta(seconds=s) for s in range(-half_s, half_s + 1, step_s)]
    sat = satrec_for(rec)
    pos = propagate_many(sat, times)
    lats, lons, alts = pos["lat"], pos["lon"], pos["alt_km"]
    heads = headings_deg(lats, lons)
    side = -90.0 if spec.look == "left" else 90.0
    near_pts: list[list[float]] = []
    far_pts: list[list[float]] = []
    for i in range(len(times) - 1):
        if not np.isfinite(lats[i]) or not np.isfinite(heads[i]) or not np.isfinite(alts[i]):
            continue
        g_near, g_far = display_ranges_km(float(alts[i]), spec)
        if not np.isfinite(g_near) or not np.isfinite(g_far) or g_far <= g_near:
            continue
        bearing = (float(heads[i]) + side) % 360.0
        nlat, nlon = destination(float(lats[i]), float(lons[i]), bearing, float(g_near))
        flat, flon = destination(float(lats[i]), float(lons[i]), bearing, float(g_far))
        near_pts.append([nlon, nlat])
        far_pts.append([flon, flat])
    if len(far_pts) < 2:
        return {"type": "Feature", "geometry": None, "properties": {"error": "swath unavailable"}}
    ring = far_pts + near_pts[::-1]
    ring.append(ring[0])
    lons_only = [p[0] for p in ring]
    if max(lons_only) - min(lons_only) > 180:
        return {
            "type": "Feature",
            "geometry": None,
            "properties": {"error": "swath crosses the antimeridian; pick another time"},
        }
    label = "possible coverage" if rec.coverage == "possible" else "approximate swath"
    return {
        "type": "Feature",
        "properties": {
            "norad": rec.norad,
            "name": rec.name,
            "family": rec.family,
            "coverage": rec.coverage,
            "label": label,
            "note": rec.note,
            "color": rec.color,
            "look": "right-looking example" if spec.look != "left" else "left-looking",
        },
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }
