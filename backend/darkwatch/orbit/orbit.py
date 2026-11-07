"""SGP4 propagation from CelesTrak OMM records to WGS84 geodetic.

TEME to ECEF uses Greenwich sidereal time, matching satellite.js.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
from sgp4.api import Satrec
from sgp4.conveniences import jday_datetime, sat_epoch_datetime
from sgp4.exporter import export_tle
from sgp4.omm import initialize
from sgp4.propagation import gstime

WGS84_A = 6378.137
WGS84_F = 1.0 / 298.257223563
WGS84_B = WGS84_A * (1.0 - WGS84_F)
WGS84_E2 = 1.0 - (WGS84_B * WGS84_B) / (WGS84_A * WGS84_A)
WGS84_EP2 = (WGS84_A * WGS84_A) / (WGS84_B * WGS84_B) - 1.0

# Alpha-5 alphabet used when a catalog number no longer fits 5 TLE digits.
_ALPHA5 = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return ensure_utc(value)
    text = value.strip().replace("Z", "+00:00")
    return ensure_utc(datetime.fromisoformat(text))


def alpha5(norad: int) -> str:
    """Encode a NORAD id into the 5-character TLE field."""
    if norad < 0:
        raise ValueError(norad)
    if norad < 100000:
        return f"{norad:05d}"
    hi, lo = divmod(norad, 10000)
    if hi >= len(_ALPHA5):
        hi = len(_ALPHA5) - 1
        lo = norad % 10000
    return _ALPHA5[hi] + f"{lo:04d}"


def _tle_checksum(line68: str) -> str:
    total = 0
    for ch in line68[:68]:
        if ch.isdigit():
            total += int(ch)
        elif ch == "-":
            total += 1
    return str(total % 10)


def _stamp_satnum(line: str, field5: str) -> str:
    body = line[:2] + field5 + line[7:68]
    body = body[:68].ljust(68)
    return body + _tle_checksum(body)


def satrec_from_omm(fields: dict) -> Satrec:
    """Build a Satrec from a CelesTrak GP / OMM JSON object."""
    f = dict(fields)
    epoch = str(f["EPOCH"])
    if "." not in epoch:
        epoch = epoch + ".000000"
    head, frac = epoch.split(".", 1)
    frac = "".join(ch for ch in frac if ch.isdigit())
    f["EPOCH"] = head + "." + (frac + "000000")[:6]
    for key in ("EPHEMERIS_TYPE", "ELEMENT_SET_NO", "REV_AT_EPOCH", "NORAD_CAT_ID"):
        f[key] = int(float(f[key]))
    if "CLASSIFICATION_TYPE" not in f or not f["CLASSIFICATION_TYPE"]:
        f["CLASSIFICATION_TYPE"] = "U"
    if "OBJECT_ID" not in f or not f["OBJECT_ID"]:
        f["OBJECT_ID"] = "2026-000A"
    sat = Satrec()
    initialize(sat, f)
    sat.satnum_str = f"{int(f['NORAD_CAT_ID']) % 100000:05d}"
    return sat


def tle_lines(sat: Satrec, norad: int) -> tuple[str, str]:
    """Classic two-line elements for satellite.js.

    Catalog numbers above 99999 are written with Alpha-5 in the satnum field.
    Mean elements are unchanged. Pass math on the server uses the OMM Satrec,
    not this rounded TLE.
    """
    if not getattr(sat, "satnum_str", None):
        sat.satnum_str = f"{int(norad) % 100000:05d}"
    if not getattr(sat, "classification", None):
        sat.classification = "U"
    if not getattr(sat, "intldesg", None):
        sat.intldesg = "00000A  "
    line1, line2 = export_tle(sat)
    field = alpha5(int(norad))
    return _stamp_satnum(line1, field), _stamp_satnum(line2, field)


def teme_to_ecef(r, gmst: float) -> tuple[float, float, float]:
    x, y, z = float(r[0]), float(r[1]), float(r[2])
    c = math.cos(gmst)
    s = math.sin(gmst)
    return (c * x + s * y, -s * x + c * y, z)


def ecef_to_geodetic(x: float, y: float, z: float) -> tuple[float, float, float]:
    """Bowring. Returns latitude degrees, longitude degrees, altitude km."""
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    theta = math.atan2(z * WGS84_A, p * WGS84_B)
    st, ct = math.sin(theta), math.cos(theta)
    lat = math.atan2(
        z + WGS84_EP2 * WGS84_B * st**3,
        p - WGS84_E2 * WGS84_A * ct**3,
    )
    sl = math.sin(lat)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sl * sl)
    alt = p / math.cos(lat) - n
    return math.degrees(lat), math.degrees(lon), alt


def ecef_to_geodetic_many(x, y, z):
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    theta = np.arctan2(z * WGS84_A, p * WGS84_B)
    st, ct = np.sin(theta), np.cos(theta)
    lat = np.arctan2(z + WGS84_EP2 * WGS84_B * st**3, p - WGS84_E2 * WGS84_A * ct**3)
    sl = np.sin(lat)
    n = WGS84_A / np.sqrt(1.0 - WGS84_E2 * sl * sl)
    alt = p / np.cos(lat) - n
    return np.degrees(lat), np.degrees(lon), alt


def propagate_one(sat: Satrec, when: datetime) -> dict | None:
    when = ensure_utc(when)
    jd, fr = jday_datetime(when)
    err, r, _v = sat.sgp4(jd, fr)
    if err != 0:
        return None
    gmst = gstime(jd + fr)
    x, y, z = teme_to_ecef(r, gmst)
    lat, lon, alt = ecef_to_geodetic(x, y, z)
    return {"lat": lat, "lon": lon, "alt_km": alt}


def propagate_many(sat: Satrec, times: list[datetime]) -> dict[str, np.ndarray]:
    if not times:
        empty = np.array([])
        return {"lat": empty, "lon": empty, "alt_km": empty, "ok": np.array([], dtype=bool)}
    jd = np.empty(len(times), dtype=np.float64)
    fr = np.empty(len(times), dtype=np.float64)
    for i, t in enumerate(times):
        jd[i], fr[i] = jday_datetime(ensure_utc(t))
    err, r, _v = sat.sgp4_array(jd, fr)
    gmst = np.array([gstime(float(jd[i] + fr[i])) for i in range(len(times))])
    c = np.cos(gmst)
    s = np.sin(gmst)
    x = c * r[:, 0] + s * r[:, 1]
    y = -s * r[:, 0] + c * r[:, 1]
    z = r[:, 2]
    lat, lon, alt = ecef_to_geodetic_many(x, y, z)
    ok = np.asarray(err) == 0
    lat = np.where(ok, lat, np.nan)
    lon = np.where(ok, lon, np.nan)
    alt = np.where(ok, alt, np.nan)
    return {"lat": lat, "lon": lon, "alt_km": alt, "ok": ok}


def epoch_of(sat: Satrec) -> datetime:
    return ensure_utc(sat_epoch_datetime(sat))
