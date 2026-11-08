"""Precomputed classifier scores, persistence review, and nearby-AIS context.

Scores in ``data/demo/evidence/evidence.json`` were computed offline on the
native 10 m scene. This module does not relabel the 21 / 18 / 3 scene counts.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from functools import lru_cache

from darkwatch import paths
from darkwatch.orbit.geometry import haversine_km
from darkwatch.orbit.orbit import parse_time
from darkwatch.storage import get_snapshot, open_store, traffic_query

PROVENANCE = "computed offline on the native 10 m scene"
CHIP_ROOT = "/evidence/"


@lru_cache(maxsize=1)
def load() -> dict:
    path = paths.evidence_dir() / "evidence.json"
    if not path.is_file():
        return {"model": {}, "detections": {}}
    return json.loads(path.read_text())


def detection_entry(det_id: str) -> dict | None:
    return (load().get("detections") or {}).get(det_id)


def chip_url(ev: dict | None) -> str | None:
    if not ev or not ev.get("chip"):
        return None
    return CHIP_ROOT + ev["chip"]


def persistence_block(ev: dict | None) -> dict | None:
    if not ev:
        return None
    pers = ev.get("persistence")
    if not pers:
        return None
    strip = pers.get("strip")
    return {
        "strip_url": (CHIP_ROOT + strip) if strip else None,
        "verdict": pers.get("verdict"),
        "reviewed_by": pers.get("reviewed"),
        "passes_covering": list(pers.get("passes_covering") or []),
    }


def candidate_status(match: dict, ev: dict | None) -> str:
    if match.get("matched"):
        return "matched"
    if ev is None:
        return "unreviewed"
    verdict = (ev.get("persistence") or {}).get("verdict")
    if ev.get("vessel_like") and verdict != "persistent":
        return "dark_candidate"
    return "deprioritized"


def enrich_match(row: dict) -> dict:
    """Copy a match row and add classifier fields. Existing keys stay as they are."""
    ev = detection_entry(row["id"])
    out = dict(row)
    out["vessel_score"] = None if not ev else ev.get("vessel_score")
    out["vessel_like"] = None if not ev else ev.get("vessel_like")
    out["candidate_status"] = candidate_status(row, ev)
    out["chip_url"] = chip_url(ev)
    out["persistence"] = persistence_block(ev)
    return out


def review_block(rows: list[dict]) -> dict:
    dark, depri, unrev = [], [], []
    for row in rows:
        status = candidate_status(row, detection_entry(row["id"]))
        if status == "dark_candidate":
            dark.append(row["id"])
        elif status == "deprioritized":
            depri.append(row["id"])
        elif status == "unreviewed":
            unrev.append(row["id"])
    return {"dark_candidates": dark, "deprioritized": depri, "unreviewed": unrev}


def _iso(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _vessels_from_sample(lat: float, lon: float, radius_km: float, t0: datetime, t1: datetime, limit: int = 40) -> list[dict]:
    """Same question as the store, answered from the committed AIS CSV when DuckDB is locked."""
    from darkwatch.ais import load_tracks
    from darkwatch.storage import box

    south, north, west, east = box(lat, lon, radius_km)
    grouped: dict[str, dict] = {}
    for mmsi, fixes in load_tracks().items():
        for fix in fixes:
            if not (t0 <= fix.t < t1):
                continue
            if not (south <= fix.lat <= north and west <= fix.lon <= east):
                continue
            if haversine_km(lat, lon, fix.lat, fix.lon) > radius_km:
                continue
            row = grouped.setdefault(
                mmsi,
                {"mmsi": mmsi, "name": fix.name or "Unknown", "pings": 0, "start": fix.t, "end": fix.t},
            )
            row["pings"] += 1
            row["start"] = min(row["start"], fix.t)
            row["end"] = max(row["end"], fix.t)
            if fix.name:
                row["name"] = fix.name
    vessels = sorted(grouped.values(), key=lambda item: item["pings"], reverse=True)[:limit]
    for item in vessels:
        item["start"] = _iso(item["start"])
        item["end"] = _iso(item["end"])
    return vessels


def _vessels(lat: float, lon: float, radius_km: float, t0: datetime, t1: datetime) -> list[dict]:
    remote = traffic_query(lat, lon, radius_km, t0, t1)
    if remote is not None and remote.get("vessels"):
        return list(remote["vessels"])
    db = open_store()
    if db.ready():
        found = list(db.vessels_between(lat, lon, radius_km, t0, t1))
        if found:
            return found
    return _vessels_from_sample(lat, lon, radius_km, t0, t1)


def _hhmm(when: datetime) -> str:
    return when.strftime("%H:%M")


def _range_km(values: list[float]) -> str:
    lo, hi = min(values), max(values)
    if lo == hi:
        return f"{lo:.1f} km"
    return f"{lo:.1f}–{hi:.1f} km"


def _summary(n: int, radius_km: float, t0: datetime, t1: datetime, annotated: list[dict]) -> str:
    window = f"{_hhmm(t0)} and {_hhmm(t1)} UTC"
    if n == 0:
        return f"No vessels reported AIS within {radius_km:g} km between {window}."
    noun = "vessel" if n == 1 else "vessels"
    head = f"{n} {noun} reported AIS within {radius_km:g} km between {window}"
    other = [v for v in annotated if v.get("matched_detection")]
    if not other:
        return head + "; none were matched to other detections at the time of the pass."
    dists = [v["matched_detection_km"] for v in other if v.get("matched_detection_km") is not None]
    span = _range_km(dists) if dists else "an unknown distance"
    if len(other) == n:
        who = "it was" if n == 1 else f"all {n} were"
    else:
        who = f"{len(other)} of {n} {'was' if len(other) == 1 else 'were'}"
    return head + f"; {who} matched to other detections {span} away at the time of the pass."


def ais_context(det: dict, scene_time: datetime, radius_km: float = 5, window_min: int = 30) -> dict:
    """Vessels near ``det`` in the ±window, annotated with the AIS match they belong to."""
    if scene_time.tzinfo is None:
        from datetime import timezone

        scene_time = scene_time.replace(tzinfo=timezone.utc)
    t0 = scene_time - timedelta(minutes=window_min)
    t1 = scene_time + timedelta(minutes=window_min)
    raw = _vessels(det["lat"], det["lon"], radius_km, t0, t1 + timedelta(seconds=1))
    snap = get_snapshot()
    by_mmsi = {row["mmsi"]: row for row in (snap.matches or []) if row.get("mmsi")}
    annotated = []
    for vessel in raw:
        item = dict(vessel)
        other = by_mmsi.get(item.get("mmsi"))
        if other and other.get("id") != det.get("id"):
            dist = haversine_km(det["lat"], det["lon"], other["lat"], other["lon"])
            item["matched_detection"] = other["id"]
            item["matched_detection_km"] = round(dist, 1)
        else:
            item["matched_detection"] = None
            item["matched_detection_km"] = None
        annotated.append(item)
    return {
        "vessels": annotated,
        "summary": _summary(len(annotated), radius_km, t0, t1, annotated),
        "radius_km": radius_km,
        "window_min": window_min,
        "start": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": t1.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def classifier_block(det_id: str) -> dict:
    from darkwatch.detection import classifier

    ev = detection_entry(det_id)
    try:
        thresh = classifier.threshold()
    except FileNotFoundError:
        thresh = (load().get("model") or {}).get("threshold")
    return {
        "score": None if not ev else ev.get("vessel_score"),
        "threshold": thresh,
        "vessel_like": None if not ev else ev.get("vessel_like"),
        "chip_url": chip_url(ev),
        "provenance": PROVENANCE,
    }


def model_payload() -> dict:
    from darkwatch.detection import classifier

    block = dict(load().get("model") or {})
    block["available"] = classifier.available()
    try:
        block["threshold"] = classifier.threshold()
    except FileNotFoundError:
        pass
    return block


def evidence_payload(row: dict, scene_time: datetime | None = None) -> dict:
    if scene_time is None:
        summary = get_snapshot().summary or {}
        scene_time = parse_time(summary["scene_time"])
    ev = detection_entry(row["id"])
    return {
        "id": row["id"],
        "detection": enrich_match(row),
        "classifier": classifier_block(row["id"]),
        "persistence": persistence_block(ev),
        "ais_context": ais_context(row, scene_time),
        "candidate_status": candidate_status(row, ev),
    }
