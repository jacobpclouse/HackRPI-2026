"""Where the SAR catalog comes from: CelesTrak, the local cache, or the snapshot.

Order: in-memory copy, fresh cache (``data/cache/sar_gp.json``, 12 h), a live
CelesTrak GP query, then the stale cache, then the committed snapshot
(``data/snapshot/sar_gp.json``). Objects that come back but cannot image
(debris, Sentinel-1B, altitudes outside the SAR LEO band) are returned in
``skipped`` with a reason.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from darkwatch import paths
from darkwatch.catalog.records import Catalog, SatRecord, record_from_omm

logger = logging.getLogger("darkwatch.catalog")

CELESTRAK = "https://celestrak.org/NORAD/elements/gp.php"
USER_AGENT = "DarkWatch/1.0 (hackathon demo; educational maritime awareness)"
CACHE_HOURS = 12
# After a failed live fetch, serve the fallback for this long before retrying.
RETRY_AFTER_S = 600

NAME_QUERIES = [
    "SENTINEL-1",
    "RCM-",
    "RADARSAT-2",
    "NISAR",
    "ICEYE",
    "CAPELLA",
    "UMBRA",
    "TERRASAR",
    "TANDEM",
    "PAZ",
    "SKYMED",
    "CSG",
    "ALOS-2",
    "ALOS-4",
    "SAOCOM",
    "KOMPSAT-5",
    "NOVASAR",
    "RISAT-2",
    "EOS-4",
    "ASNARO-2",
    "STRIX",
    "QPS-SAR",
    "GAOFEN-3",
    "HAIYANG-3",
    "PIESAT",
]

_lock = threading.Lock()
_mem: Catalog | None = None
_last_failure = 0.0


def cache_path() -> Path:
    return paths.cache_dir() / "sar_gp.json"


def snapshot_path() -> Path:
    return paths.snapshot_dir() / "sar_gp.json"


def fetch_remote() -> Catalog:
    skipped: list[dict] = []
    seen: set[int] = set()
    raws: list[dict] = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=45, follow_redirects=True) as client:
        for name in NAME_QUERIES:
            try:
                response = client.get(CELESTRAK, params={"NAME": name, "FORMAT": "JSON"})
            except httpx.HTTPError as exc:
                skipped.append({"name": name, "norad": None, "reason": f"query failed: {exc}"})
                continue
            if response.status_code != 200:
                skipped.append(
                    {"name": name, "norad": None, "reason": f"CelesTrak HTTP {response.status_code}"}
                )
                time.sleep(0.15)
                continue
            try:
                payload = response.json()
            except json.JSONDecodeError:
                skipped.append({"name": name, "norad": None, "reason": "non-JSON response"})
                continue
            if isinstance(payload, dict):
                skipped.append(
                    {"name": name, "norad": None, "reason": str(payload.get("error") or "no objects")}
                )
                time.sleep(0.15)
                continue
            for obj in payload:
                try:
                    norad = int(obj["NORAD_CAT_ID"])
                except (KeyError, TypeError, ValueError):
                    continue
                if norad in seen:
                    continue
                seen.add(norad)
                raws.append(obj)
            time.sleep(0.15)
    sats: list[SatRecord] = []
    for raw in raws:
        rec, skip = record_from_omm(raw)
        if rec:
            sats.append(rec)
        elif skip:
            skipped.append(skip)
    sats.sort(key=lambda s: (s.coverage != "systematic", s.family, s.name))
    return Catalog(
        fetched_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        source=CELESTRAK,
        satellites=sats,
        skipped=skipped,
        origin="live",
    )


def write(cat: Catalog, path: Path | None = None) -> None:
    path = path or cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = {
        "fetched_at": cat.fetched_at,
        "source": cat.source,
        "satellites": [s.to_blob() for s in cat.satellites],
        "skipped": cat.skipped,
    }
    path.write_text(json.dumps(blob))


def read(path: Path, origin: str = "cache") -> Catalog:
    blob = json.loads(path.read_text())
    return Catalog(
        fetched_at=blob.get("fetched_at") or "",
        source=blob.get("source") or CELESTRAK,
        satellites=[SatRecord.from_blob(row) for row in blob.get("satellites") or []],
        skipped=blob.get("skipped") or [],
        origin=origin,
    )


def age_hours(cat: Catalog) -> float | None:
    try:
        fetched = datetime.fromisoformat(cat.fetched_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - fetched).total_seconds() / 3600.0


def fresh(cat: Catalog) -> bool:
    age = age_hours(cat)
    return age is not None and age < CACHE_HOURS


def _fallback(reason: str) -> Catalog | None:
    if cache_path().exists():
        cat = read(cache_path(), origin="stale-cache")
        if cat.satellites:
            cat.notes.append(reason)
            return cat
    if snapshot_path().exists():
        cat = read(snapshot_path(), origin="snapshot")
        cat.notes.append(reason)
        return cat
    return None


def get_catalog(refresh: bool = False) -> Catalog:
    global _mem, _last_failure
    with _lock:
        if _mem is not None and not refresh:
            if fresh(_mem):
                return _mem
            if _mem.origin in ("stale-cache", "snapshot") and time.time() - _last_failure < RETRY_AFTER_S:
                return _mem
        if not refresh and cache_path().exists():
            cached = read(cache_path(), origin="cache")
            if fresh(cached) and cached.satellites:
                _mem = cached
                return cached
        try:
            cat = fetch_remote()
        except Exception as exc:
            logger.warning("CelesTrak fetch failed: %s", exc)
            cat = None
            reason = f"CelesTrak fetch failed: {exc}"
        else:
            reason = "CelesTrak returned no SAR objects"
        if cat is not None and cat.satellites:
            write(cat)
            _mem = cat
            return cat
        _last_failure = time.time()
        fallback = _fallback(reason)
        if fallback is not None:
            logger.info("serving %s SAR catalog from %s", len(fallback.satellites), fallback.origin)
            _mem = fallback
            return fallback
        if cat is not None:
            _mem = cat
            return cat
        raise RuntimeError(reason)


def status() -> dict:
    """Catalog provenance for /api/health. Does not trigger a fetch."""
    cat = _mem
    if cat is None:
        for path, origin in ((cache_path(), "cache"), (snapshot_path(), "snapshot")):
            if path.exists():
                cat = read(path, origin=origin)
                break
    if cat is None:
        return {"origin": "missing", "fetched_at": None, "age_h": None, "count": 0}
    age = age_hours(cat)
    return {
        "origin": cat.origin,
        "fetched_at": cat.fetched_at,
        "age_h": None if age is None else round(age, 2),
        "count": len(cat.satellites),
        "loaded": _mem is not None,
    }
