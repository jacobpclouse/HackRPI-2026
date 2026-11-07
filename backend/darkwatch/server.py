"""DarkWatch HTTP API and static globe."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from darkwatch import __version__, config, paths
from darkwatch.ais import ais_silences, annotate_overlap, load_tracks, onset_after_pass
from darkwatch.catalog import SYSTEMATIC_FAMILIES, get_catalog
from darkwatch.catalog import status as catalog_status
from darkwatch.detection import coverage_report, floor_now, sentinel_validation
from darkwatch.geo import REGIONS
from darkwatch.orbit import Gap, parse_time, swath_polygon
from darkwatch.services import audio_dir, gemini_brief, sar_presence_report, script_for, synthesize
from darkwatch.storage import get_snapshot, open_store, ping_tracks, report_from_stored, traffic_query

logger = logging.getLogger("darkwatch.api")

app = FastAPI(title="DarkWatch", version=__version__)
app.add_middleware(GZipMiddleware, minimum_size=800)

_store = None


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        {"error": str(exc.detail), "detail": exc.detail, "status": exc.status_code, "path": request.url.path},
        status_code=exc.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    problems = []
    for err in exc.errors():
        where = ".".join(str(part) for part in err.get("loc", ()) if part not in ("query", "path", "body"))
        problems.append(f"{where}: {err.get('msg')}" if where else str(err.get("msg")))
    message = "Invalid request. " + "; ".join(problems)
    return JSONResponse(
        {"error": message, "detail": message, "status": 400, "path": request.url.path},
        status_code=400,
    )


def store():
    global _store
    if _store is None or not _store.ready():
        _store = open_store()
    return _store


def _read_json(name: str):
    path = paths.demo_dir() / name
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _scene_summary() -> dict | None:
    try:
        return get_snapshot().summary
    except Exception:
        return _read_json("summary.json")


def _matches() -> list[dict]:
    try:
        return get_snapshot().matches
    except Exception:
        return _read_json("matches.json") or []


@lru_cache(maxsize=1)
def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=paths.root(),
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


@app.get("/api/health")
def health():
    summary = _scene_summary()
    snap = get_snapshot()
    cat = catalog_status()
    fallbacks = []
    if cat["origin"] in ("snapshot", "stale-cache", "missing"):
        fallbacks.append("catalog")
    remote = config.integrations()
    if snap.source == "bundle" and (remote["tiger"] or remote["sql_warehouse"]):
        fallbacks.append("scene")
    if config.tiger_database_url() and store().kind == "duckdb":
        fallbacks.append("store")
    return {
        "ok": True,
        "version": __version__,
        "git_sha": _git_sha(),
        "scene_ready": summary is not None,
        "scene_id": None if not summary else summary.get("scene_id"),
        "catalog": cat,
        "integrations": config.integrations(),
        "data": snap.status(),
        "store": store().status(),
        "fallbacks": fallbacks,
    }


@app.get("/config.js")
def config_js():
    body = {
        "ionToken": config.cesium_ion_token(),
        "fishConfigured": bool(config.fish_audio_api_key()),
    }
    return Response(
        f"window.DARKWATCH_CONFIG = {json.dumps(body)};",
        media_type="application/javascript",
    )


@app.get("/api/regions")
def regions():
    return {"regions": REGIONS}


@app.get("/api/satellites")
def satellites(refresh: bool = False):
    try:
        cat = get_catalog(refresh=refresh)
    except Exception as exc:
        raise HTTPException(503, f"CelesTrak catalog unavailable: {exc}") from exc
    families: dict[str, int] = {}
    for sat in cat.satellites:
        families[sat.family] = families.get(sat.family, 0) + 1
    return {
        "fetched_at": cat.fetched_at,
        "source": cat.source,
        "origin": cat.origin,
        "count": len(cat.satellites),
        "families": families,
        "systematic_families": SYSTEMATIC_FAMILIES,
        "satellites": [sat.to_public() for sat in cat.satellites],
        "skipped": cat.skipped,
    }


@app.get("/api/swath")
def swath(norad: int, at: str | None = None):
    cat = get_catalog()
    rec = cat.get(norad)
    if rec is None:
        raise HTTPException(404, "Satellite is not in the SAR catalog")
    when = parse_time(at) if at else datetime.now(timezone.utc)
    return swath_polygon(rec, when)


@app.get("/api/coverage")
def coverage(
    lat: float | None = Query(None),
    lon: float | None = Query(None),
    hours: float = 48,
    start: str | None = None,
    families: str | None = None,
):
    if lat is None or lon is None:
        raise HTTPException(400, "lat and lon are required query parameters, in decimal degrees")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(400, "lat/lon out of range")
    if hours <= 0 or hours > 96:
        raise HTTPException(400, "hours must be between 0 and 96")
    gap_families = [f.strip() for f in families.split(",") if f.strip()] if families else None
    t0 = parse_time(start) if start else None
    try:
        return coverage_report(lat, lon, t0, hours, gap_families)
    except Exception as exc:
        raise HTTPException(503, f"Pass prediction failed: {exc}") from exc


@app.get("/api/scene")
def scene():
    snap = get_snapshot()
    if not snap.summary or not snap.meta:
        raise HTTPException(404, "Scene sample is missing. Run make prepare.")
    return {"summary": snap.summary, "meta": snap.meta, "source": snap.source}


@app.get("/api/scene/preview.png")
def scene_preview():
    snap = get_snapshot()
    if snap.preview:
        return Response(content=snap.preview, media_type="image/png")
    path = paths.demo_dir() / "scene_preview.png"
    if not path.exists():
        raise HTTPException(404, "Scene preview missing")
    return FileResponse(path, media_type="image/png")


@app.get("/api/detections")
def detections():
    rows = _matches()
    if not rows and not (paths.demo_dir() / "matches.json").exists():
        raise HTTPException(404, "Detections missing. Run make prepare.")
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {k: v for k, v in row.items() if k not in ("lat", "lon")},
                "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
            }
            for row in rows
        ],
    }


@app.get("/api/ais")
def ais():
    tracks = get_snapshot().tracks
    if not tracks:
        raise HTTPException(404, "AIS tracks missing. Run make prepare.")
    return tracks


@app.get("/api/mpas")
def mpas():
    path = paths.demo_dir() / "mpas.geojson"
    if not path.exists():
        return {"type": "FeatureCollection", "features": [], "properties": {"note": "No MPA sample yet"}}
    return json.loads(path.read_text())


def _gap_objects(report: dict) -> list[Gap]:
    out = []
    for gap in report["gaps"]:
        out.append(
            Gap(
                start=parse_time(gap["start"]),
                end=parse_time(gap["end"]),
                duration_s=gap["duration_s"],
            )
        )
    return out


def _gap_passes(report: dict) -> list[dict]:
    """The systematic passes that decide the report's gaps."""
    fams = set(report.get("gap_families") or SYSTEMATIC_FAMILIES)
    return [p for p in report["passes"] if p["coverage"] == "systematic" and p["family"] in fams]


@app.get("/api/story")
def story(families: str | None = None):
    """Scene-day gaps, AIS silences, and the next 48 hours for the Kattegat chip."""
    snap = get_snapshot()
    summary = snap.summary
    meta = snap.meta
    if not summary or not meta:
        raise HTTPException(404, "Scene sample is missing. Run make prepare.")
    west, south, east, north = meta["bbox"]
    lat = (south + north) / 2
    lon = (west + east) / 2
    scene_time = parse_time(summary["scene_time"])
    day0 = scene_time.replace(hour=0, minute=0, second=0, microsecond=0)
    gap_families = [f.strip() for f in families.split(",") if f.strip()] if families else None
    day = report_from_stored(snap.passes, "scene_day", day0, day0 + timedelta(hours=24), gap_families)
    if day is None:
        day = coverage_report(lat, lon, day0, 24, gap_families)
    upcoming_start = floor_now()
    upcoming = None
    try:
        upcoming = coverage_report(lat, lon, upcoming_start, 48, gap_families)
    except Exception:
        upcoming = report_from_stored(
            snap.passes, "upcoming", upcoming_start, upcoming_start + timedelta(hours=48), gap_families
        )
    if upcoming is None:
        raise HTTPException(503, "Pass prediction failed and no stored passes are available.")
    validation = sentinel_validation(day, scene_time)
    tracks = ping_tracks(snap.pings) if snap.pings is not None else load_tracks()
    silences = ais_silences(tracks, tuple(meta["bbox"]), min_gap_s=1800)
    annotated = annotate_overlap(silences, _gap_objects(day))
    overlapping = [row for row in annotated if row["overlaps_coverage_gap"]]
    baseline = onset_after_pass(
        silences, _gap_passes(day), window_min=30, day_start=day0, day_end=day0 + timedelta(hours=24)
    )
    baseline["meaning"] = (
        "Fraction of AIS silences that start within 30 minutes after a systematic pass ends, "
        "against the fraction of the day those post-pass windows cover. "
        "If p_value is above 0.05, this sample does not show timing beyond chance."
    )
    return {
        "summary": summary,
        "meta": {
            "scene_id": meta["scene_id"],
            "datetime": meta["datetime"],
            "platform": meta.get("platform"),
            "orbit_state": meta.get("orbit_state"),
            "bbox": meta["bbox"],
        },
        "observed_acquisition": {
            "time": summary["scene_time"],
            "scene_id": summary["scene_id"],
            "platform": meta.get("platform"),
            "source": "Planetary Computer STAC timestamp, not an SGP4 estimate",
        },
        "validation": validation,
        "scene_day": day,
        "upcoming": upcoming,
        "ais_silences": annotated[:25],
        "ais_silence_count": len(annotated),
        "silences_overlapping_gap": len(overlapping),
        "intent_baseline": baseline,
        "ethics": summary.get("note"),
        "data_source": snap.source,
        "refreshed_at": snap.refreshed_at,
    }


@app.get("/api/traffic")
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


@app.get("/api/briefs/{det_id}")
def brief(det_id: str):
    summary = _scene_summary() or {}
    row = next((r for r in _matches() if r["id"] == det_id), None)
    if row is None:
        raise HTTPException(404, "Unknown detection")
    if row.get("matched"):
        return {
            "provider": "template",
            "text": (
                f"{det_id} matches public AIS {row.get('name') or row.get('mmsi')} "
                f"at {row.get('match_km')} km. It is not an unmatched detection."
            ),
        }
    return gemini_brief(row, summary)


@app.post("/api/narrate")
def narrate(which: str = "opening", det_id: str | None = None):
    text = script_for("opening")
    key = "opening"
    if which == "candidate" and det_id:
        summary = _scene_summary() or {}
        row = next((r for r in _matches() if r["id"] == det_id), None)
        if row is None:
            raise HTTPException(404, "Unknown detection")
        text = gemini_brief(row, summary)["text"]
        key = f"candidate-{det_id}"
    result = synthesize(key, text)
    result["text"] = text
    return result


@app.get("/api/narration/{name}")
def narration_file(name: str):
    if "/" in name or not name.endswith(".mp3"):
        raise HTTPException(400, "Bad audio name")
    path = audio_dir() / name
    if not path.exists():
        raise HTTPException(404, "Audio not generated")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/validation/gfw")
def gfw():
    summary = _scene_summary()
    meta = _read_json("scene_meta.json")
    if not summary or not meta:
        raise HTTPException(404, "Scene sample is missing")
    day = summary["scene_time"][:10]
    end = (parse_time(summary["scene_time"]) + timedelta(days=1)).strftime("%Y-%m-%d")
    return sar_presence_report(meta["bbox"], day, end, int(summary.get("detections") or 0))


app.mount("/", StaticFiles(directory=str(paths.frontend_dir()), html=True), name="ui")
