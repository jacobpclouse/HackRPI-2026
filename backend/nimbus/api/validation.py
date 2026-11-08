"""/api/validation/gfw."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException

from nimbus.api.common import read_demo_json, scene_summary
from nimbus.orbit import parse_time
from nimbus.services import sar_presence_report

router = APIRouter()


@router.get("/api/validation/gfw")
def gfw():
    summary = scene_summary()
    meta = read_demo_json("scene_meta.json")
    if not summary or not meta:
        raise HTTPException(404, "Scene sample is missing")
    day = summary["scene_time"][:10]
    end = (parse_time(summary["scene_time"]) + timedelta(days=1)).strftime("%Y-%m-%d")
    return sar_presence_report(meta["bbox"], day, end, int(summary.get("detections") or 0))
