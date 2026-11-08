"""Sentinel-1 discovery and tiles. Disabled until CDSE OAuth is configured."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from darkwatch.services import copernicus
from darkwatch.storage import get_snapshot

router = APIRouter()


class SearchIn(BaseModel):
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-85, le=85)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-85, le=85)
    start: datetime
    end: datetime


def _scene():
    try:
        snap = get_snapshot()
    except Exception:
        return None
    return copernicus.scene_window(snap.meta, snap.summary)


@router.get("/api/copernicus/status")
def status():
    on = copernicus.configured()
    return {
        "configured": on,
        "state": "ready" if on else "unconfigured",
        "message": "" if on else copernicus.SETUP,
    }


@router.post("/api/copernicus/acquisitions")
def acquisitions(body: SearchIn):
    if not copernicus.configured():
        return {
            "configured": False,
            "state": "unconfigured",
            "message": copernicus.SETUP,
            "acquisitions": [],
        }
    try:
        rows, truncated = copernicus.search_acquisitions(
            body.west,
            body.south,
            body.east,
            body.north,
            body.start,
            body.end,
            _scene(),
        )
    except copernicus.Unconfigured:
        return {
            "configured": False,
            "state": "unconfigured",
            "message": copernicus.SETUP,
            "acquisitions": [],
        }
    except (copernicus.UpstreamError, ValueError) as exc:
        state = "unavailable"
        return {"configured": True, "state": state, "message": str(exc), "acquisitions": []}
    if not rows:
        return {
            "configured": True,
            "state": "no-coverage",
            "message": copernicus.NO_COVERAGE,
            "acquisitions": [],
        }
    return {"configured": True, "state": "ready", "truncated": truncated, "acquisitions": rows}


@router.get("/api/copernicus/view.png")
def view_image(
    start: str = Query(min_length=10),
    end: str = Query(min_length=10),
    polarization: str = Query(min_length=2, max_length=4),
    viz: str = Query(min_length=2, max_length=4),
    west: float = Query(),
    south: float = Query(),
    east: float = Query(),
    north: float = Query(),
    orbit: str = "",
    footprint_west: float = Query(),
    footprint_south: float = Query(),
    footprint_east: float = Query(),
    footprint_north: float = Query(),
):
    if not copernicus.configured():
        return JSONResponse(
            {"error": copernicus.SETUP, "detail": copernicus.SETUP, "status": 503},
            status_code=503,
        )
    try:
        start_at = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_at = datetime.fromisoformat(end.replace("Z", "+00:00"))
        if end_at < start_at:
            end_at = start_at + timedelta(seconds=2)
        png = copernicus.render_view(
            west,
            south,
            east,
            north,
            start_at,
            end_at,
            polarization.upper(),
            viz.upper(),
            orbit.upper() or None,
            [footprint_west, footprint_south, footprint_east, footprint_north],
        )
    except copernicus.Unconfigured:
        return JSONResponse({"error": copernicus.SETUP, "detail": copernicus.SETUP, "status": 503}, status_code=503)
    except (ValueError, copernicus.UpstreamError) as exc:
        return JSONResponse({"error": str(exc), "detail": str(exc), "status": 502}, status_code=502)
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/api/copernicus/tiles/{z}/{x}/{y}")
def tile(
    z: int,
    x: int,
    y: int,
    start: str = Query(min_length=10),
    end: str = Query(min_length=10),
    polarization: str = Query(min_length=2, max_length=4),
    viz: str = Query(min_length=2, max_length=4),
    west: float = Query(),
    south: float = Query(),
    east: float = Query(),
    north: float = Query(),
    orbit: str = "",
):
    if not copernicus.configured():
        return JSONResponse(
            {"error": copernicus.SETUP, "detail": copernicus.SETUP, "status": 503},
            status_code=503,
        )
    try:
        start_at = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_at = datetime.fromisoformat(end.replace("Z", "+00:00"))
        if end_at < start_at:
            end_at = start_at + timedelta(seconds=2)
        png = copernicus.render_tile(
            z,
            x,
            y,
            start_at,
            end_at,
            polarization.upper(),
            viz.upper(),
            orbit.upper() or None,
            [west, south, east, north],
        )
    except copernicus.Unconfigured:
        return JSONResponse({"error": copernicus.SETUP, "detail": copernicus.SETUP, "status": 503}, status_code=503)
    except (ValueError, copernicus.UpstreamError) as exc:
        return JSONResponse({"error": str(exc), "detail": str(exc), "status": 502}, status_code=502)
    return Response(content=png, media_type="image/png")
