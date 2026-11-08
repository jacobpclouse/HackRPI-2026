"""/api/satellites, /api/swath, /api/regions, /api/missions."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from nimbus.catalog import SYSTEMATIC_FAMILIES, get_catalog
from nimbus.catalog.missions import deep_links, load_missions
from nimbus.geo import REGIONS
from nimbus.orbit import parse_time, swath_polygon

router = APIRouter()


@router.get("/api/regions")
def regions():
    return {"regions": REGIONS}


@router.get("/api/satellites")
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


@router.get("/api/missions")
def missions(
    family: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    at: str | None = None,
):
    registry = load_missions()
    if family is None:
        return {"missions": registry}
    spec = registry.get(family)
    if spec is None:
        raise HTTPException(404, f"No mission registry entry for {family}")
    out = dict(spec)
    if lat is not None and lon is not None:
        when = parse_time(at) if at else datetime.now(timezone.utc)
        out["deep_links"] = deep_links(family, lat, lon, when)
    return out


@router.get("/api/swath")
def swath(norad: int, at: str | None = None):
    cat = get_catalog()
    rec = cat.get(norad)
    if rec is None:
        raise HTTPException(404, "Satellite is not in the SAR catalog")
    when = parse_time(at) if at else datetime.now(timezone.utc)
    return swath_polygon(rec, when)
