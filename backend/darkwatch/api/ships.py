"""/api/ships/global and /api/ships/global/{mmsi}."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from darkwatch import config
from darkwatch.ais import global_cache
from darkwatch.ais.stream import ship_dict

router = APIRouter()


def _age_s(fetched_at: str | None) -> int | None:
    if not fetched_at:
        return None
    try:
        when = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int((datetime.now(timezone.utc) - when).total_seconds()))


def _payload(state: global_cache.CacheState) -> dict:
    body = global_cache.to_payload(state)
    body["meta"] = {
        "source": state.source,
        "fetched_at": state.fetched_at,
        "age_s": _age_s(state.fetched_at),
        "count": len(state.ships),
        "excluded_bbox": state.excluded_bbox or global_cache.excluded_bbox(),
        "refresh_enabled": config.ais_global_refresh() and bool(config.aisstream_api_key()),
        "last_error": state.last_error,
    }
    return body


@router.get("/api/ships/global")
def ships_global():
    return _payload(global_cache.current())


@router.get("/api/ships/global/{mmsi}")
def ships_one(mmsi: str):
    state = global_cache.current()
    ship = state.ships.get(str(mmsi))
    if ship is None:
        raise HTTPException(404, "Unknown MMSI")
    return ship_dict(ship)


def health_block() -> dict:
    state = global_cache.current()
    return {
        "source": state.source,
        "count": len(state.ships),
        "age_s": _age_s(state.fetched_at),
        "refresh_enabled": config.ais_global_refresh() and bool(config.aisstream_api_key()),
        "last_error": state.last_error,
    }
