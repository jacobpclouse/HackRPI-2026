"""Deterministic facts dict for a Kattegat dark-candidate report.

Every number on the page and every number Gemini is allowed to use comes from
this module. Cache is per (candidate, horizon); generated_at is stamped on read.
"""

from __future__ import annotations

import json
import math
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import box as shp_box

from darkwatch import paths
from darkwatch.casefile.candidates import acquisition_time, require_dark_candidate, scene_block
from darkwatch.casefile.plan import plan_for
from darkwatch.casefile.reach import SPEED_KN, geodesic_disk, projected_area_m2, reach_radius_km
from darkwatch.casefile.recommend import GFW_URL, LIMITS
from darkwatch.catalog.missions import load_missions
from darkwatch.detection import classifier
from darkwatch.geo.reference import clip_to_sea, jurisdiction, nearest_ports
from darkwatch.services.evidence import ais_context, detection_entry, model_payload, persistence_block

REPORT_VERSION = "1"
MARKING = "UNVERIFIED · FOR VERIFICATION"
HORIZONS_H = (1.0, 3.0, 6.0, 12.0)
DEFAULT_HORIZON_H = 3.0
PATROL_KN = 20.0
SEARCH_SPEED_KN = 12.0
CHIP_M_PER_PX = 10.0
CHIP_NATIVE_PX = 64
FOOTPRINT_RANGE_FRAC = 0.65
FOOTPRINT_MEDIAN_FACTOR = 1.35
MPA_NEAR_KM = 2.0
AIS_RADIUS_KM = 5.0
NEXT_PASS_N = 5
AUTHORITIES = (
    {"country": "Denmark", "label": "Danish Maritime Authority", "url": "https://dma.dk"},
    {"country": "Sweden", "label": "Swedish Coast Guard", "url": "https://www.kustbevakningen.se"},
)
PRIORITY_RULE = (
    "HIGH if vessel-like (score at or above the classifier threshold) and transient "
    "and no AIS within 5 km and inside or within 2 km of a protected area; "
    "MEDIUM if vessel-like and transient; LOW otherwise."
)
FOOTPRINT_METHOD = (
    f"Major axis of the largest connected bright blob on the {CHIP_NATIVE_PX}×{CHIP_NATIVE_PX} "
    f"{CHIP_M_PER_PX:.0f} m evidence chip (display PNGs are integer-upscaled; metres-per-pixel is scaled back). "
    f"Pixels above median + {FOOTPRINT_RANGE_FRAC}×(max−median); fallback {FOOTPRINT_MEDIAN_FACTOR}× median. "
    "Length is 2√(3λ) of the blob covariance (uniform-blob width). "
    "Reported as a range. Radar footprint, approximate; SAR smearing tends to overstate length."
)
DDM_RE = re.compile(
    r"(\d+)\s*°\s*(\d+(?:\.\d+)?)\s*[′']\s*([NS])\s*,\s*(\d+)\s*°\s*(\d+(?:\.\d+)?)\s*[′']\s*([EW])",
    re.I,
)

_cache: dict[tuple[str, float], dict] = {}
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _human_utc(dt) -> str:
    return dt.strftime("%d %b %Y %H:%M UTC")


def format_ddm(lat: float, lon: float) -> str:
    def _one(value: float, pos: str, neg: str, width: int) -> str:
        hemi = pos if value >= 0 else neg
        absv = abs(float(value))
        deg = int(absv)
        minutes = (absv - deg) * 60.0
        return f"{deg:0{width}d}° {minutes:06.3f}′ {hemi}"

    return f"{_one(lat, 'N', 'S', 2)}, {_one(lon, 'E', 'W', 3)}"


def parse_ddm(text: str) -> tuple[float, float]:
    match = DDM_RE.search(text or "")
    if not match:
        raise ValueError(f"not a DDM pair: {text!r}")
    lat_d, lat_m, lat_h, lon_d, lon_m, lon_h = match.groups()
    lat = int(lat_d) + float(lat_m) / 60.0
    lon = int(lon_d) + float(lon_m) / 60.0
    if lat_h.upper() == "S":
        lat = -lat
    if lon_h.upper() == "W":
        lon = -lon
    return lat, lon


def _tier(score: float | None, threshold: float | None) -> str:
    if score is None:
        return "low"
    if score >= 0.95:
        return "high"
    if threshold is not None and score >= float(threshold):
        return "medium"
    return "low"


def measure_footprint(chip_rel: str | None) -> dict | None:
    """Approximate radar-footprint length from the 10 m evidence chip."""
    if not chip_rel:
        return None
    path = paths.evidence_dir() / chip_rel
    if not path.is_file():
        return None
    try:
        import numpy as np
        from PIL import Image
        from scipy import ndimage
    except ImportError:
        return None
    img = np.asarray(Image.open(path).convert("L"), dtype=float)
    if img.size == 0:
        return None
    m_per_px = CHIP_M_PER_PX * CHIP_NATIVE_PX / float(img.shape[0])
    median = float(np.median(img))
    peak = float(img.max())
    thresh = median + FOOTPRINT_RANGE_FRAC * (peak - median)
    mask = img >= thresh
    if mask.mean() > 0.08 or not mask.any():
        thresh = median * FOOTPRINT_MEDIAN_FACTOR
        mask = img >= thresh
        if mask.mean() > 0.08:
            thresh = float(np.quantile(img, 0.97))
            mask = img >= thresh
    if not mask.any():
        return None
    labeled, nlab = ndimage.label(mask)
    if nlab < 1:
        return None
    sizes = ndimage.sum(mask, labeled, index=list(range(1, nlab + 1)))
    idx = int(np.argmax(sizes)) + 1
    ys, xs = np.where(labeled == idx)
    cap_m = CHIP_NATIVE_PX * math.sqrt(2.0) * CHIP_M_PER_PX
    if xs.size < 2:
        major_m = m_per_px
    else:
        coords = np.column_stack((xs.astype(float), ys.astype(float)))
        cov = np.cov(coords, rowvar=False)
        evals = np.linalg.eigvalsh(np.atleast_2d(cov))
        major_px = 2.0 * math.sqrt(3.0 * max(float(np.max(evals)), 0.0))
        major_m = max(m_per_px, major_px * m_per_px)
    major_m = min(major_m, cap_m)
    lo = int(max(10, round(major_m * 0.75 / 10.0) * 10))
    hi = int(max(lo + 10, round(major_m * 1.15 / 10.0) * 10))
    return {
        "length_m_range": f"≈ {lo}–{hi} m",
        "length_m_lo": lo,
        "length_m_hi": hi,
        "major_m": round(major_m, 1),
        "note": "radar footprint, approximate; SAR smearing tends to overstate length",
        "method": FOOTPRINT_METHOD,
    }


def compute_priority(
    *,
    vessel_like: bool,
    transient: bool,
    ais_within_5km: bool,
    mpa_inside_or_within_2km: bool,
) -> dict:
    reasons = []
    if vessel_like:
        reasons.append("vessel-like")
    if transient:
        reasons.append("transient")
    if not ais_within_5km:
        reasons.append("no AIS within 5 km")
    if mpa_inside_or_within_2km:
        reasons.append("inside or within 2 km of a protected area")
    if vessel_like and transient and (not ais_within_5km) and mpa_inside_or_within_2km:
        tier = "HIGH"
    elif vessel_like and transient:
        tier = "MEDIUM"
    else:
        tier = "LOW"
    return {"tier": tier, "reasons": reasons, "rule": PRIORITY_RULE}


def _mission(family: str) -> dict:
    spec = load_missions().get(family) or {}
    return {
        "family": family,
        "name": spec.get("name") or family,
        "operator": spec.get("operator") or family,
        "band": spec.get("band"),
        "access": spec.get("access") or "unknown",
        "access_note": spec.get("note") or "",
        "links": list(spec.get("links") or []),
    }


def _access_label(access: str) -> str:
    return {
        "open": "open",
        "open-sample": "sample",
        "restricted": "restricted",
        "commercial": "commercial",
    }.get(access, access)


def _disk_stats(lat: float, lon: float, hours: float, kn: float) -> dict:
    radius = reach_radius_km(hours, kn)
    disk = geodesic_disk(lat, lon, radius)
    clipped, used = clip_to_sea(disk)
    area_km2 = round(projected_area_m2(clipped, lat, lon) / 1e6, 1)
    return {
        "hours": hours,
        "speed_kn": kn,
        "radius_km": round(radius, 2),
        "area_km2": area_km2,
        "clipped_to_sea": used,
    }


def _search_box(lat: float, lon: float, hours: float) -> dict:
    radius = reach_radius_km(hours, SEARCH_SPEED_KN)
    disk = geodesic_disk(lat, lon, radius)
    clipped, used = clip_to_sea(disk)
    minx, miny, maxx, maxy = clipped.bounds if not clipped.is_empty else disk.bounds
    corners = {
        "sw": {"lat": round(miny, 5), "lon": round(minx, 5)},
        "se": {"lat": round(miny, 5), "lon": round(maxx, 5)},
        "ne": {"lat": round(maxy, 5), "lon": round(maxx, 5)},
        "nw": {"lat": round(maxy, 5), "lon": round(minx, 5)},
    }
    for key, pt in corners.items():
        pt["ddm"] = format_ddm(pt["lat"], pt["lon"])
        pt["name"] = key.upper()
    return {
        "horizon_h": hours,
        "speed_kn": SEARCH_SPEED_KN,
        "west": round(minx, 5),
        "south": round(miny, 5),
        "east": round(maxx, 5),
        "north": round(maxy, 5),
        "corners": corners,
        "clipped_to_sea": used,
        "contains_disk": True,
        "note": "Axis-aligned lat/lon box of the 12 kn reach disk at the chosen horizon.",
    }


def _authorities(nearest_country: str | None) -> list[dict]:
    rows = [dict(item) for item in AUTHORITIES]
    if nearest_country:
        rows.sort(key=lambda item: 0 if item["country"] == nearest_country else 1)
    return rows


def _next_passes(plan: dict) -> tuple[list[dict], dict | None]:
    raw = list(plan.get("passes") or [])[:NEXT_PASS_N]
    out = []
    for item in raw:
        family = item.get("family") or ""
        spec = _mission(family)
        fr = item.get("coverage_frac") or {}
        out.append(
            {
                "norad": item.get("norad"),
                "satellite": item.get("name"),
                "family": family,
                "operator": spec["operator"],
                "band": spec["band"],
                "coverage": item.get("coverage"),
                "access": spec["access"],
                "access_label": _access_label(spec["access"]),
                "access_note": spec["access_note"],
                "links": spec["links"],
                "start": item.get("center") or item.get("start"),
                "hours_after": item.get("hours_after"),
                "coverage_pct": {
                    "slow": round(float(fr.get("slow") or 0) * 100),
                    "typical": round(float(fr.get("typical") or 0) * 100),
                    "fast": round(float(fr.get("fast") or 0) * 100),
                },
                "best_next": False,
                "color": item.get("color"),
            }
        )
    systematic = [p for p in out if p["coverage"] == "systematic"]
    best = min(systematic, key=lambda p: p["start"] or "") if systematic else None
    if best:
        best["best_next"] = True
    return out, best


def _candidate_actions(row: dict, facts_bits: dict) -> list[dict]:
    actions = []
    best = facts_bits.get("best_next")
    if best:
        actions.append(
            {
                "id": "review_pass",
                "title": "Review the best systematic pass",
                "facts": {
                    "satellite": best["satellite"],
                    "family": best["family"],
                    "time": best["start"],
                    "hours_after": best["hours_after"],
                    "coverage_typical_pct": best["coverage_pct"]["typical"],
                    "access": best["access"],
                    "access_label": best["access_label"],
                    "access_note": best["access_note"],
                    "links": best["links"],
                },
            }
        )
    box = facts_bits["search_box"]
    port = (facts_bits.get("nearest_ports") or [None])[0]
    actions.append(
        {
            "id": "patrol_search",
            "title": "On-water or aerial check of the search box",
            "facts": {
                "horizon_h": box["horizon_h"],
                "corners": box["corners"],
                "nearest_port": None
                if not port
                else {
                    "name": port["name"],
                    "country": port.get("country"),
                    "distance_km": port["distance_km"],
                    "bearing_compass": port["bearing_compass"],
                    "transit_h_20kn": port.get("transit_h_20kn"),
                },
            },
        }
    )
    actions.append(
        {
            "id": "ais_history",
            "title": "Check Global Fishing Watch for vessel presence and AIS gaps",
            "facts": {
                "url": GFW_URL,
                "west": box["west"],
                "south": box["south"],
                "east": box["east"],
                "north": box["north"],
            },
        }
    )
    if (row.get("in_mpa") or row.get("near_mpa")) and row.get("mpa_name"):
        actions.append(
            {
                "id": "mpa_rules",
                "title": "Compare against the protected-area management rules",
                "facts": {
                    "name": row["mpa_name"],
                    "in_mpa": bool(row.get("in_mpa")),
                    "mpa_km": row.get("mpa_km"),
                    "designation": "Natura 2000",
                },
            }
        )
    jur = facts_bits.get("jurisdiction") or {}
    actions.append(
        {
            "id": "notify",
            "title": "Refer to the Kattegat authorities",
            "facts": {
                "nearest_coast_country": jur.get("nearest_coast_country"),
                "method": jur.get("method") or JURISDICTION_FALLBACK,
                "authorities": facts_bits["authorities"],
            },
        }
    )
    tasked = [p for p in facts_bits.get("next_passes") or [] if p.get("coverage") == "tasked"]
    if not tasked:
        for item in plan_for(row["id"]).get("passes") or []:
            if item.get("coverage") == "tasked":
                spec = _mission(item.get("family") or "")
                tasked.append(
                    {
                        "satellite": item.get("name"),
                        "family": item.get("family"),
                        "start": item.get("center"),
                        "hours_after": item.get("hours_after"),
                        "access": spec["access"],
                        "links": spec["links"],
                        "operator": spec["operator"],
                    }
                )
                break
    if tasked:
        first = tasked[0]
        actions.append(
            {
                "id": "task_commercial",
                "title": "Optional commercial tasking of the earliest tasked pass",
                "facts": {
                    "satellite": first.get("satellite"),
                    "operator": first.get("operator"),
                    "time": first.get("start"),
                    "hours_after": first.get("hours_after"),
                    "access": first.get("access"),
                    "links": first.get("links") or [],
                },
            }
        )
    return actions


JURISDICTION_FALLBACK = (
    "Approximate: nearest coastline and 12 nm distance. Official maritime boundaries were not computed."
)


def _notes(missing: list[str]) -> list[str]:
    if not missing:
        return []
    return [f"reference layer unavailable: {', '.join(missing)}"]


def _build(det_id: str, horizon_h: float) -> dict:
    row = require_dark_candidate(det_id)
    t_acq = acquisition_time()
    scene = scene_block()
    lat, lon = float(row["lat"]), float(row["lon"])
    ev = detection_entry(det_id) or {}
    model = model_payload()
    try:
        threshold = classifier.threshold()
    except FileNotFoundError:
        threshold = model.get("threshold")
    score = ev.get("vessel_score")
    vessel_like = bool(ev.get("vessel_like"))
    pers = persistence_block(ev)
    transient = bool(pers and pers.get("verdict") == "transient")
    ais = ais_context(row, t_acq, radius_km=AIS_RADIUS_KM)
    nearest_ais = row.get("nearest_ais_km")
    ais_within_5km = nearest_ais is not None and float(nearest_ais) <= AIS_RADIUS_KM
    mpa_close = bool(row.get("in_mpa")) or (
        row.get("mpa_km") is not None and float(row["mpa_km"]) <= MPA_NEAR_KM
    )
    jur = jurisdiction(lat, lon)
    ports = nearest_ports(lat, lon, n=3)
    missing = []
    if jur is None:
        missing.append("countries")
        jur = {
            "nearest_coast_country": None,
            "distance_to_coast_km": None,
            "likely_territorial_sea": None,
            "method": JURISDICTION_FALLBACK,
        }
    if ports is None:
        missing.append("ports")
        ports = []
    if ports:
        dist = ports[0]["distance_km"]
        hours = dist / (PATROL_KN * 1.852)
        ports[0]["transit_h_20kn"] = round(hours, 2)
        ports[0]["transit_note"] = f"Approximate transit at an assumed patrol speed of {PATROL_KN:.0f} kn."
    plan = plan_for(det_id)
    next_passes, best_next = _next_passes(plan)
    growth = []
    any_clipped = False
    for hours in HORIZONS_H:
        row_g = {"horizon_h": hours, "speeds": {}}
        for key, kn in SPEED_KN.items():
            stats = _disk_stats(lat, lon, hours, kn)
            row_g["speeds"][key] = stats
            any_clipped = any_clipped or stats["clipped_to_sea"]
        growth.append(row_g)
    search_box = _search_box(lat, lon, horizon_h)
    disk_12 = geodesic_disk(lat, lon, reach_radius_km(horizon_h, SEARCH_SPEED_KN))
    box_poly = shp_box(search_box["west"], search_box["south"], search_box["east"], search_box["north"])
    search_box["contains_disk"] = box_poly.covers(disk_12) or box_poly.contains(disk_12.centroid)
    footprint = measure_footprint(ev.get("chip"))
    authorities = _authorities(jur.get("nearest_coast_country"))
    priority = compute_priority(
        vessel_like=vessel_like,
        transient=transient,
        ais_within_5km=ais_within_5km,
        mpa_inside_or_within_2km=mpa_close,
    )
    bits = {
        "best_next": best_next,
        "search_box": search_box,
        "nearest_ports": ports,
        "jurisdiction": jur,
        "next_passes": next_passes,
        "authorities": authorities,
    }
    actions = _candidate_actions(row, bits)
    test = (model.get("test") or {}) if isinstance(model, dict) else {}
    return {
        "case": {
            "id": det_id,
            "scene_id": scene.get("scene_id"),
            "acquisition_time": _iso(t_acq),
            "acquisition_time_human": _human_utc(t_acq),
            "generated_at": _now(),
            "report_version": REPORT_VERSION,
            "marking": MARKING,
            "horizon_h": horizon_h,
            "platform": scene.get("platform"),
        },
        "target": {
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "position_ddm": format_ddm(lat, lon),
            "peak_db": row.get("peak_db"),
            "shore_km": row.get("shore_km"),
            "confidence": {
                "score": score,
                "threshold": threshold,
                "tier": _tier(None if score is None else float(score), threshold),
                "vessel_like": vessel_like,
            },
            "footprint": footprint,
            "chip_url": None if not ev.get("chip") else "/evidence/" + ev["chip"],
        },
        "jurisdiction": {
            **jur,
            "protected_area": {
                "name": row.get("mpa_name"),
                "in_mpa": bool(row.get("in_mpa")),
                "near_mpa": bool(row.get("near_mpa")),
                "mpa_km": row.get("mpa_km"),
            },
        },
        "nearest_ports": ports,
        "search_area": {
            "growth": growth,
            "clipped_to_sea": any_clipped or search_box["clipped_to_sea"],
            "search_box": search_box,
            "speeds_kn": dict(SPEED_KN),
        },
        "ais_context": {
            "summary": ais.get("summary"),
            "radius_km": ais.get("radius_km"),
            "window_min": ais.get("window_min"),
            "start": ais.get("start"),
            "end": ais.get("end"),
            "within_5km": ais_within_5km,
            "count": len(ais.get("vessels") or []),
            "accounted_for": sum(1 for v in (ais.get("vessels") or []) if v.get("matched_detection")),
            "nearest_ais_km": nearest_ais,
            "vessels": [
                {
                    "name": v.get("name"),
                    "mmsi": v.get("mmsi"),
                    "start": v.get("start"),
                    "end": v.get("end"),
                    "matched_detection": v.get("matched_detection"),
                    "matched_detection_km": v.get("matched_detection_km"),
                }
                for v in (ais.get("vessels") or [])
            ],
        },
        "persistence": pers,
        "next_passes": next_passes,
        "best_next": best_next,
        "candidate_actions": actions,
        "priority": priority,
        "method": {
            "model": {
                "arch": model.get("arch"),
                "file": model.get("file"),
                "threshold": threshold,
                "test": test,
            },
            "data_sources": [
                {
                    "name": "Sentinel-1 RTC (Planetary Computer)",
                    "scene_id": scene.get("scene_id"),
                    "time": scene.get("datetime"),
                },
                {"name": "Danish Maritime Authority AIS", "time": scene.get("datetime")},
                {"name": "Natural Earth 10m ports, land, countries", "license": "public domain"},
                {"name": "EEA Natura 2000", "note": "packaged Kattegat subset"},
            ],
            "assumptions": [
                "Slow 6 kn, typical 12 kn, and fast 20 kn are constant-speed assumptions, not tracks.",
                "Reach areas assume constant speed and ignore routing.",
                "Radar footprint is approximate; SAR smearing tends to overstate length.",
                JURISDICTION_FALLBACK,
                PRIORITY_RULE,
            ],
            "footprint_method": FOOTPRINT_METHOD,
        },
        "limits": LIMITS.split(" Reach areas")[0]
        if " Reach areas" in LIMITS
        else (
            "No public AIS is not evidence of wrongdoing. Small vessels are not required to carry AIS, "
            "state vessels often do not broadcast, and reception can fail."
        ),
        "notes": _notes(missing),
        "authorities": authorities,
    }


def build_facts(det_id: str, horizon_h: float = DEFAULT_HORIZON_H) -> dict:
    horizon = float(horizon_h)
    if horizon not in HORIZONS_H:
        horizon = DEFAULT_HORIZON_H
    key = (det_id, horizon)
    with _lock:
        cached = _cache.get(key)
    if cached is not None:
        out = json.loads(json.dumps(cached))
        out["case"]["generated_at"] = _now()
        return out
    facts = _build(det_id, horizon)
    stored = json.loads(json.dumps(facts))
    with _lock:
        _cache[key] = stored
    return facts


def clear_facts_cache() -> None:
    with _lock:
        _cache.clear()


def validate_horizon(raw: float | int | str | None) -> float:
    if raw is None or raw == "":
        return DEFAULT_HORIZON_H
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("horizon_h must be 1, 3, 6, or 12") from exc
    if value not in HORIZONS_H:
        raise ValueError("horizon_h must be 1, 3, 6, or 12")
    return value


def chip_path(det_id: str) -> Path | None:
    ev = detection_entry(det_id) or {}
    rel = ev.get("chip")
    if not rel:
        return None
    path = paths.evidence_dir() / rel
    return path if path.is_file() else None
