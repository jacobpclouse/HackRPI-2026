"""Background AISStream refresh. One task; never crashes the app."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from darkwatch import config
from darkwatch.ais import global_cache
from darkwatch.ais.stream import pull

logger = logging.getLogger("darkwatch.ais.refresh")

_task: asyncio.Task | None = None
_running = False


def refresh_enabled() -> bool:
    return config.ais_global_refresh() and bool(config.aisstream_api_key())


async def run_once() -> None:
    global _running
    if _running:
        return
    _running = True
    t0 = time.monotonic()
    previous = global_cache.current()
    prev_n = len(previous.ships)
    try:
        result = await pull(config.aisstream_api_key(), config.ais_global_listen_s())
        now = datetime.now(timezone.utc)
        error = result.error
        merged = global_cache.merge(
            previous.ships,
            result.ships,
            now,
            config.ais_global_max_age_h(),
            config.ais_global_max_ships(),
        )
        ok, reason = global_cache.should_accept(result.n_position_reports, len(merged), prev_n)
        duration = time.monotonic() - t0
        if not ok:
            previous.last_error = error or reason
            global_cache.set_current(previous)
            logger.info(
                "AISStream refresh kept-previous received=%s kept=%s reason=%s duration=%.1fs",
                result.n_position_reports,
                prev_n,
                previous.last_error,
                duration,
            )
            return
        state = global_cache.CacheState(
            ships=merged,
            fetched_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            source="live",
            last_error=None,
            excluded_bbox=global_cache.excluded_bbox(),
        )
        global_cache.save(state)
        logger.info(
            "AISStream refresh accepted received=%s kept=%s previous=%s duration=%.1fs",
            result.n_position_reports,
            len(merged),
            prev_n,
            duration,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("AISStream refresh failed")
        previous.last_error = "connection failed"
        global_cache.set_current(previous)
    finally:
        _running = False


async def _loop() -> None:
    await asyncio.sleep(5)
    while True:
        try:
            await run_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("AISStream refresh loop")
        await asyncio.sleep(max(60, config.ais_global_interval_min() * 60))


def start() -> None:
    global _task
    if not refresh_enabled():
        logger.info("AISStream refresh off (set AIS_GLOBAL_REFRESH=1 and AISSTREAM_API_KEY)")
        return
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop(), name="ais-global-refresh")


async def stop() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
