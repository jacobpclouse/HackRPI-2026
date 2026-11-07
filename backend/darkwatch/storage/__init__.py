"""AIS and detection storage, and where results are read from.

TIGER_DATABASE_URL, when set, is a Tiger Data / TimescaleDB Postgres URL
(``storage/timescale.py``). Any connection or extension failure falls back to
a local DuckDB file (``storage/duckdb.py``) so the demo still answers "who
was near here". ``storage/live.py`` picks the newest scene: Tiger, then the
SQL warehouse, then the bundled demo.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from pathlib import Path

from darkwatch import config, paths

logger = logging.getLogger("darkwatch.storage")


def duck_path() -> Path:
    return paths.cache_dir() / "darkwatch.duckdb"


def ais_csv() -> Path:
    return paths.demo_dir() / "ais_pings.csv.gz"


def matches_json() -> Path:
    return paths.demo_dir() / "matches.json"


class Store:
    """Answers "who reported AIS near here between t0 and t1"."""

    kind = "none"

    def ready(self) -> bool:
        return False

    def vessels_between(self, lat, lon, radius_km, t0, t1, limit=40):
        return []

    def buckets(self, lat, lon, radius_km, t0, t1):
        return []

    def status(self) -> dict:
        return {"kind": self.kind, "ready": self.ready()}


def box(lat, lon, radius_km):
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * max(0.2, math.cos(math.radians(lat))))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def open_store() -> Store:
    from darkwatch.storage.duckdb import DuckStore
    from darkwatch.storage.timescale import TigerStore

    url = config.tiger_database_url()
    if url:
        try:
            return TigerStore(url)
        except Exception as exc:
            logger.warning("Tiger store unavailable, using DuckDB: %s", exc)
            duck = DuckStore()
            duck.fallback_reason = str(exc)
            return duck
    if ais_csv().exists():
        try:
            return DuckStore()
        except Exception as exc:
            logger.warning("DuckDB store unavailable: %s", exc)
            return Store()
    return Store()


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# Submodules import Store and the helpers above, so they load after them.
from darkwatch.storage.duckdb import DuckStore  # noqa: E402
from darkwatch.storage.live import (  # noqa: E402
    Snapshot,
    get_snapshot,
    load_bundle,
    ping_tracks,
    report_from_stored,
    traffic_query,
)
from darkwatch.storage.timescale import TigerStore  # noqa: E402

__all__ = [
    "DuckStore",
    "Snapshot",
    "Store",
    "TigerStore",
    "ais_csv",
    "box",
    "duck_path",
    "get_snapshot",
    "load_bundle",
    "matches_json",
    "open_store",
    "parse_dt",
    "ping_tracks",
    "report_from_stored",
    "traffic_query",
]
