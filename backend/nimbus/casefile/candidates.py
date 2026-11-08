"""Resolve Kattegat dark candidates from the evidence service. IDs are not hardcoded."""

from __future__ import annotations

from nimbus.orbit.orbit import parse_time
from nimbus.services.evidence import candidate_status, detection_entry
from nimbus.storage import get_snapshot


class NotDarkCandidate(LookupError):
    pass


def match_rows() -> list[dict]:
    snap = get_snapshot()
    return list(snap.matches or [])


def match_row(det_id: str) -> dict | None:
    return next((row for row in match_rows() if row["id"] == det_id), None)


def is_dark_candidate(row: dict) -> bool:
    return candidate_status(row, detection_entry(row["id"])) == "dark_candidate"


def dark_ids() -> list[str]:
    return [row["id"] for row in match_rows() if is_dark_candidate(row)]


def require_dark_candidate(det_id: str) -> dict:
    row = match_row(det_id)
    if row is None or not is_dark_candidate(row):
        raise NotDarkCandidate(det_id)
    return row


def acquisition_time():
    snap = get_snapshot()
    meta = snap.meta or {}
    summary = snap.summary or {}
    raw = meta.get("datetime") or summary.get("scene_time")
    if not raw:
        raise RuntimeError("scene acquisition time is missing")
    return parse_time(raw)


def scene_block() -> dict:
    snap = get_snapshot()
    meta = snap.meta or {}
    summary = snap.summary or {}
    return {
        "scene_id": meta.get("scene_id") or summary.get("scene_id"),
        "datetime": meta.get("datetime") or summary.get("scene_time"),
        "platform": meta.get("platform"),
    }
