"""On-disk global AIS cache. Accept-or-keep; atomic replace; Kattegat excluded."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from nimbus import paths
from nimbus.ais.stream import Ship, ship_from_row

logger = logging.getLogger("nimbus.ais.cache")

FIELDS = ["mmsi", "name", "lat", "lon", "sog", "cog", "heading", "category", "last_report"]
SCENE_BUFFER_DEG = 0.05
MIN_REPORTS = 500


@dataclass
class CacheState:
    ships: dict[str, Ship] = field(default_factory=dict)
    fetched_at: str | None = None
    source: str = "empty"  # live | cached | seed | empty
    last_error: str | None = None
    excluded_bbox: list[float] | None = None


_memory: CacheState | None = None
_mtime: float | None = None


def scene_bbox() -> list[float]:
    meta_path = paths.demo_dir() / "scene_meta.json"
    meta = json.loads(meta_path.read_text())
    return list(meta["bbox"])


def excluded_bbox(buffer: float = SCENE_BUFFER_DEG) -> list[float]:
    west, south, east, north = scene_bbox()
    return [round(west - buffer, 4), round(south - buffer, 4), round(east + buffer, 4), round(north + buffer, 4)]


def in_bbox(lat: float, lon: float, bbox: list[float]) -> bool:
    west, south, east, north = bbox
    return south <= lat <= north and west <= lon <= east


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def from_payload(data: dict, source: str) -> CacheState:
    fields = data.get("fields") or FIELDS
    box = data.get("excluded_bbox") or excluded_bbox()
    ships = {}
    for row in data.get("rows") or []:
        ship = ship_from_row(fields, row)
        if ship.mmsi and not in_bbox(ship.lat, ship.lon, box):
            ships[ship.mmsi] = ship
    return CacheState(
        ships=ships,
        fetched_at=data.get("fetched_at"),
        source=source,
        last_error=data.get("last_error"),
        excluded_bbox=box,
    )


def to_payload(state: CacheState) -> dict:
    return {
        "fetched_at": state.fetched_at,
        "fields": FIELDS,
        "rows": [ship.to_row() for ship in state.ships.values()],
        "last_error": state.last_error,
        "excluded_bbox": state.excluded_bbox or excluded_bbox(),
    }


def load_file(path: Path, source: str) -> CacheState | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return from_payload(data, source)


def load() -> CacheState:
    """Runtime cache if it parses; otherwise seed; otherwise empty."""
    cached = load_file(paths.ais_global_cache(), "cached")
    if cached and cached.ships:
        return cached
    seed = load_file(paths.ais_global_seed(), "seed")
    if seed and seed.ships:
        return seed
    if seed:
        return seed
    return CacheState(source="empty", excluded_bbox=excluded_bbox())


def current(force: bool = False) -> CacheState:
    """In-memory copy, reloaded when the cache file mtime changes."""
    global _memory, _mtime
    path = paths.ais_global_cache()
    seed = paths.ais_global_seed()
    watch = path if path.is_file() else seed
    mtime = watch.stat().st_mtime if watch.is_file() else None
    if _memory is None or force or mtime != _mtime:
        _memory = load()
        _mtime = mtime
    return _memory


def set_current(state: CacheState) -> None:
    global _memory, _mtime
    _memory = state
    cache = paths.ais_global_cache()
    _mtime = cache.stat().st_mtime if cache.is_file() else _mtime


def merge(
    previous: dict[str, Ship],
    fresh: dict[str, Ship],
    now: datetime,
    max_age_h: float,
    max_ships: int,
    bbox: list[float] | None = None,
) -> dict[str, Ship]:
    box = bbox or excluded_bbox()
    cutoff = now.timestamp() - max_age_h * 3600
    out = dict(previous)
    out.update(fresh)
    kept: dict[str, Ship] = {}
    for mmsi, ship in out.items():
        if in_bbox(ship.lat, ship.lon, box):
            continue
        reported = _parse_time(ship.last_report)
        if reported is not None and reported.timestamp() < cutoff:
            continue
        kept[mmsi] = ship

    if len(kept) <= max_ships:
        return kept

    def rank(item: tuple[str, Ship]) -> tuple[int, float]:
        ship = item[1]
        pri = 0 if ship.category in ("cargo", "tanker", "passenger") else 1
        reported = _parse_time(ship.last_report)
        ts = reported.timestamp() if reported else 0.0
        return (pri, -ts)

    ranked = sorted(kept.items(), key=rank)
    return dict(ranked[:max_ships])


def should_accept(n_reports: int, merged_n: int, previous_n: int) -> tuple[bool, str | None]:
    if n_reports < MIN_REPORTS:
        return False, f"only {n_reports} reports"
    if previous_n and merged_n < 0.5 * previous_n:
        return False, f"merged {merged_n} is under 50% of previous {previous_n}"
    return True, None


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".ais_global.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save(state: CacheState, path: Path | None = None) -> None:
    target = path or paths.ais_global_cache()
    atomic_write(target, to_payload(state))
    set_current(state)
