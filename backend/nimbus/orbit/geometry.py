"""Spherical geometry and SAR ground-range helpers.

Cross-track sign is positive to the right of the velocity heading.
"""

from __future__ import annotations

import math

import numpy as np

EARTH_KM = 6371.0


def wrap_lon(lon: float) -> float:
    return (lon + 180.0) % 360.0 - 180.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(y, x)) % 360.0


def destination(lat: float, lon: float, bearing: float, dist_km: float) -> tuple[float, float]:
    if dist_km <= 0:
        return lat, wrap_lon(lon)
    delta = dist_km / EARTH_KM
    theta = math.radians(bearing)
    p1 = math.radians(lat)
    l1 = math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(delta) + math.cos(p1) * math.sin(delta) * math.cos(theta))
    l2 = l1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(p1),
        math.cos(delta) - math.sin(p1) * math.sin(p2),
    )
    return math.degrees(p2), wrap_lon(math.degrees(l2))


def along_cross_km(
    track_lat: float, track_lon: float, heading_deg: float, lat: float, lon: float
) -> tuple[float, float]:
    """Return along-track and right-positive cross-track offsets in km."""
    dist = haversine_km(track_lat, track_lon, lat, lon)
    brg = bearing_deg(track_lat, track_lon, lat, lon)
    delta = (brg - heading_deg + 540.0) % 360.0 - 180.0
    rad = math.radians(delta)
    return dist * math.cos(rad), dist * math.sin(rad)


def along_cross_km_many(lat, lon, heading_deg, plat: float, plon: float):
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    heading_deg = np.asarray(heading_deg, dtype=float)
    phi1 = np.radians(lat)
    phi2 = math.radians(plat)
    dphi = np.radians(plat - lat)
    dl = np.radians(plon - lon)
    a = np.sin(dphi / 2.0) ** 2 + np.cos(phi1) * math.cos(phi2) * np.sin(dl / 2.0) ** 2
    dist = 2 * EARTH_KM * np.arcsin(np.minimum(1.0, np.sqrt(np.clip(a, 0, 1))))
    y = np.sin(dl) * math.cos(phi2)
    x = np.cos(phi1) * math.sin(phi2) - np.sin(phi1) * math.cos(phi2) * np.cos(dl)
    brg = np.degrees(np.arctan2(y, x)) % 360.0
    delta = (brg - heading_deg + 540.0) % 360.0 - 180.0
    rad = np.radians(delta)
    return dist * np.cos(rad), dist * np.sin(rad)


def ground_range_km(alt_km: float, incidence_deg: float, r_km: float = EARTH_KM) -> float:
    """Arc distance from the sub-satellite point to a given incidence angle.

    Uses the spherical relation sin(off-nadir) = R/(R+h) * sin(incidence),
    earth-central angle = incidence - off-nadir.
    """
    if not math.isfinite(alt_km) or alt_km <= 1:
        return float("nan")
    inc = math.radians(incidence_deg)
    arg = (r_km / (r_km + alt_km)) * math.sin(inc)
    if arg <= 0 or arg >= 1:
        return float("nan")
    theta = math.asin(arg)
    gamma = inc - theta
    if gamma <= 0:
        return float("nan")
    return r_km * gamma


def headings_deg(lat, lon) -> np.ndarray:
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    n = len(lat)
    h = np.full(n, np.nan)
    if n < 2:
        return h
    phi1 = np.radians(lat[:-1])
    phi2 = np.radians(lat[1:])
    dl = np.radians(lon[1:] - lon[:-1])
    y = np.sin(dl) * np.cos(phi2)
    x = np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(dl)
    step = np.degrees(np.arctan2(y, x)) % 360.0
    good = np.isfinite(lat[:-1]) & np.isfinite(lat[1:])
    h[:-1] = np.where(good, step, np.nan)
    h[-1] = h[-2]
    return h
