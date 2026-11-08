"""Analyst sign-off for a case file. Newest review first. Atomic writes."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from nimbus import paths

DECISIONS = ("Verify further", "Refer", "Dismiss")
REVIEW_PATH: Path | None = None


def review_path() -> Path:
    return REVIEW_PATH or (paths.cache_dir() / "case_reviews.json")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".case_reviews.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_all() -> dict:
    path = review_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def history(det_id: str) -> list[dict]:
    rows = load_all().get(det_id) or []
    return list(rows)


def latest(det_id: str) -> dict | None:
    rows = history(det_id)
    return rows[0] if rows else None


def validate(body: dict) -> dict:
    analyst = str(body.get("analyst") or "").strip()
    decision = body.get("decision")
    notes = str(body.get("notes") or "").strip()
    if not analyst:
        raise ValueError("Analyst name is required")
    if decision not in DECISIONS:
        raise ValueError("Decision must be Verify further, Refer, or Dismiss")
    if decision in ("Dismiss", "Refer") and not notes:
        raise ValueError("Notes are required for Dismiss and Refer")
    return {"analyst": analyst, "decision": decision, "notes": notes}


def add_review(det_id: str, body: dict) -> dict:
    entry = validate(body)
    entry["signed_at"] = _now()
    payload = load_all()
    rows = list(payload.get(det_id) or [])
    rows.insert(0, entry)
    payload[det_id] = rows
    _atomic_write(review_path(), payload)
    return entry


def all_latest() -> dict:
    return {det_id: (rows[0] if rows else None) for det_id, rows in load_all().items() if rows}
