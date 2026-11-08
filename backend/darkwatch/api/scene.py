"""/api/scene, preview, detections, AIS tracks, MPAs, traffic, and the upload seam."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from darkwatch import paths
from darkwatch.ais.scene_layer import ais_only_geojson
from darkwatch.api.common import matches, store
from darkwatch.orbit import parse_time
from darkwatch.services.evidence import enrich_match, review_block
from darkwatch.storage import get_snapshot, traffic_query

router = APIRouter()


@router.get("/api/scene")
def scene():
    snap = get_snapshot()
    if not snap.summary or not snap.meta:
        raise HTTPException(404, "Scene sample is missing. Run make prepare.")
    return {
        "summary": snap.summary,
        "meta": snap.meta,
        "source": snap.source,
        "review": review_block(snap.matches or []),
    }


@router.get("/api/scene/preview.png")
def scene_preview():
    snap = get_snapshot()
    if snap.preview:
        return Response(content=snap.preview, media_type="image/png")
    path = paths.demo_dir() / "scene_preview.png"
    if not path.exists():
        raise HTTPException(404, "Scene preview missing")
    return FileResponse(path, media_type="image/png")


@router.get("/api/scene/tiles")
def scene_tiles():
    from darkwatch.imagery.tiles import load as load_tiles

    try:
        return load_tiles()
    except Exception as exc:
        raise HTTPException(
            503,
            "Radar tiles are unavailable (Planetary Computer unreachable and no cached TileJSON).",
        ) from exc


@router.post("/api/scene/upload")
async def scene_upload(
    file: UploadFile | None = File(None),
    image: UploadFile | None = File(None),
    labels: UploadFile | None = File(None),
    acquired_at: str | None = Form(None),
):
    from darkwatch.api.imagery import run_analyze

    upload = image or file
    if upload is None:
        raise HTTPException(400, "Missing image.")
    data = await upload.read()
    xml = await labels.read() if labels is not None else None
    return await run_analyze(data, upload.filename or "upload", xml, acquired_at)


@router.get("/api/detections")
def detections():
    rows = matches()
    if not rows and not (paths.demo_dir() / "matches.json").exists():
        raise HTTPException(404, "Detections missing. Run make prepare.")
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {k: v for k, v in enrich_match(row).items() if k not in ("lat", "lon")},
                "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
            }
            for row in rows
        ],
    }


@router.get("/api/scene/ais_only")
def scene_ais_only():
    try:
        return ais_only_geojson()
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc


@router.get("/api/ais")
def ais():
    tracks = get_snapshot().tracks
    if not tracks:
        raise HTTPException(404, "AIS tracks missing. Run make prepare.")
    return tracks


@router.get("/api/mpas")
def mpas():
    path = paths.demo_dir() / "mpas.geojson"
    if not path.exists():
        return {"type": "FeatureCollection", "features": [], "properties": {"note": "No MPA sample yet"}}
    return json.loads(path.read_text())


@router.get("/api/traffic")
def traffic(
    lat: float,
    lon: float,
    radius_km: float = 30,
    start: str | None = None,
    end: str | None = None,
):
    """Who reported AIS near a point between two times. Uses the active store."""
    t1 = parse_time(end) if end else datetime.now(timezone.utc)
    t0 = parse_time(start) if start else t1 - timedelta(hours=6)
    remote = traffic_query(lat, lon, radius_km, t0, t1)
    if remote is not None:
        return {"store": {"kind": remote["source"], "ready": True}, **remote}
    db = store()
    return {
        "store": db.status(),
        "vessels": db.vessels_between(lat, lon, radius_km, t0, t1),
        "buckets": db.buckets(lat, lon, radius_km, t0, t1) if db.ready() else [],
    }
