"""/api/health and /config.js."""

from __future__ import annotations

import json
import subprocess
from functools import lru_cache

from fastapi import APIRouter
from fastapi.responses import Response

from darkwatch import __version__, config, paths
from darkwatch.api.common import scene_summary, store
from darkwatch.api.ships import health_block as ais_health
from darkwatch.catalog import status as catalog_status
from darkwatch.detection import classifier
from darkwatch.geo.reference import available as reference_available
from darkwatch.storage import get_snapshot

router = APIRouter()


@lru_cache(maxsize=1)
def git_sha() -> str | None:
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


@router.get("/api/health")
def health():
    summary = scene_summary()
    snap = get_snapshot()
    cat = catalog_status()
    integrations = config.integrations()
    db = store()
    fallbacks = []
    if cat["origin"] in ("snapshot", "stale-cache", "missing"):
        fallbacks.append("catalog")
    if snap.source == "bundle" and (integrations["tiger"] or integrations["sql_warehouse"]):
        fallbacks.append("scene")
    if integrations["tiger"] and db.kind == "duckdb":
        fallbacks.append("store")
    return {
        "ok": True,
        "version": __version__,
        "git_sha": git_sha(),
        "scene_ready": summary is not None,
        "scene_id": None if not summary else summary.get("scene_id"),
        "catalog": cat,
        "integrations": integrations,
        "data": snap.status(),
        "store": db.status(),
        "fallbacks": fallbacks,
        "classifier": {
            "available": classifier.available(),
            "threshold": classifier.threshold() if classifier.threshold_path().is_file() else None,
        },
        "ais_global": ais_health(),
        "reference": reference_available(),
        "gemini": {
            "configured": bool(config.gemini_api_key()),
            "model": config.gemini_model(),
        },
    }


@router.get("/config.js")
def config_js():
    body = {
        "ionToken": config.cesium_ion_token(),
        "fishConfigured": bool(config.fish_audio_api_key()),
        "version": __version__,
    }
    return Response(
        f"window.DARKWATCH_CONFIG = {json.dumps(body)};",
        media_type="application/javascript",
    )
