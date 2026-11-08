"""/api/evidence/{id} and /api/model."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from nimbus.api.common import matches, scene_summary
from nimbus.orbit.orbit import parse_time
from nimbus.services.evidence import evidence_payload, model_payload

router = APIRouter()


@router.get("/api/model")
def model():
    return model_payload()


@router.get("/api/evidence/{det_id}")
def evidence(det_id: str):
    row = next((r for r in matches() if r["id"] == det_id), None)
    if row is None:
        raise HTTPException(404, "Unknown detection")
    summary = scene_summary() or {}
    scene_time = parse_time(summary["scene_time"]) if summary.get("scene_time") else None
    return evidence_payload(row, scene_time)
