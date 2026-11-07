"""Newest DarkWatch results: Tiger, then the SQL warehouse, then the bundled demo.

Tiger is used only when ``TIGER_DATABASE_URL`` is set and ``scenes`` has a row.
The warehouse is used only when the app platform injected ``DATABRICKS_HOST`` and
``DATABRICKS_WAREHOUSE_ID`` and the Delta tables exist. Otherwise the files in
``data/demo`` are served, so a fresh deploy works before the refresh job runs.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from darkwatch import config, paths
from darkwatch.detection.matching import Fix
from darkwatch.orbit.gaps import coverage_gaps, longest_gap
from darkwatch.orbit.orbit import parse_time
from darkwatch.orbit.passes import Pass

logger = logging.getLogger("darkwatch.storage")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_cache: "Snapshot | None" = None
_cache_at = 0.0
_TTL_S = 120.0


@dataclass
class Snapshot:
    source: str
    summary: dict
    meta: dict
    matches: list
    tracks: dict
    preview: bytes | None = None
    passes: list = field(default_factory=list)
    pings: list | None = None
    refreshed_at: str | None = None

    def status(self) -> dict:
        return {
            "source": self.source,
            "scene_id": (self.summary or {}).get("scene_id"),
            "refreshed_at": self.refreshed_at,
            "detections": len(self.matches or []),
            "passes": len(self.passes or []),
        }


def catalog_name() -> str:
    return _ident(config.darkwatch_catalog(), "workspace")


def schema_name() -> str:
    return _ident(config.darkwatch_schema(), "darkwatch")


def _ident(value: str, default: str) -> str:
    text = (value or "").strip() or default
    if not _IDENT.match(text):
        raise ValueError(f"unsafe SQL identifier {value!r}")
    return text


def _iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value).replace(" ", "T").replace("+00:00", "Z")


def _bytes(value) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytearray):
        value = bytes(value)
    return value if isinstance(value, (bytes, bytearray)) and value else None


def load_bundle() -> Snapshot:
    demo = paths.demo_dir()
    summary = json.loads((demo / "summary.json").read_text())
    meta = json.loads((demo / "scene_meta.json").read_text())
    matches = json.loads((demo / "matches.json").read_text())
    tracks = json.loads((demo / "ais_tracks.geojson").read_text())
    return Snapshot(
        source="bundle",
        summary=summary,
        meta=meta,
        matches=matches,
        tracks=tracks,
        preview=None,
        passes=[],
        pings=None,
        refreshed_at=None,
    )


def _row_match(row: dict) -> dict:
    matched = row.get("matched")
    if isinstance(matched, str):
        matched = matched.lower() in {"true", "t", "1"}
    item = {
        "id": row.get("det_id") or row.get("id"),
        "lat": row.get("lat"),
        "lon": row.get("lon"),
        "pixels": row.get("pixels"),
        "peak_db": row.get("peak_db"),
        "shore_km": row.get("shore_km"),
        "matched": bool(matched),
        "mmsi": row.get("mmsi") or None,
        "name": row.get("name") or None,
        "match_km": row.get("match_km"),
        "nearest_ais_km": row.get("nearest_ais_km"),
        "nearest_mmsi": row.get("nearest_mmsi") or None,
        "nearest_name": row.get("nearest_name") or None,
        "confidence": row.get("confidence"),
        "in_mpa": bool(row.get("in_mpa")),
        "near_mpa": bool(row.get("near_mpa")),
        "mpa_name": row.get("mpa_name") or None,
        "mpa_km": row.get("mpa_km"),
        "candidate": not bool(matched),
        "label": None if matched else "potential dark vessel",
    }
    return item


def _snapshot_from_rows(source: str, scene: dict, match_rows: list, pass_rows: list, ping_rows: list) -> Snapshot:
    summary = json.loads(scene["summary_json"]) if isinstance(scene.get("summary_json"), str) else dict(scene.get("summary_json") or {})
    tracks = json.loads(scene["tracks_json"]) if isinstance(scene.get("tracks_json"), str) else (scene.get("tracks_json") or {"type": "FeatureCollection", "features": []})
    bbox = [
        float(scene["bbox_west"]),
        float(scene["bbox_south"]),
        float(scene["bbox_east"]),
        float(scene["bbox_north"]),
    ]
    meta = {
        "scene_id": scene["scene_id"],
        "datetime": scene.get("acquired_at") or summary.get("scene_time"),
        "platform": scene.get("platform"),
        "orbit_state": scene.get("orbit_state"),
        "bbox": bbox,
    }
    summary.setdefault("scene_id", scene["scene_id"])
    summary.setdefault("scene_time", meta["datetime"])
    summary.setdefault("bbox", bbox)
    pings = []
    for row in ping_rows:
        try:
            sog = float(row["sog"]) if row.get("sog") not in (None, "") else None
        except (TypeError, ValueError):
            sog = None
        pings.append(
            Fix(
                mmsi=str(row["mmsi"]),
                t=datetime.fromisoformat(_iso(row["ts"]).replace("Z", "+00:00")),
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                name=row.get("name") or "",
                sog=sog,
            )
        )
    passes = []
    for row in pass_rows:
        passes.append(
            {
                "window_kind": row.get("window_kind"),
                "norad": int(row["norad"]),
                "name": row.get("name"),
                "family": row.get("family"),
                "coverage": row.get("coverage"),
                "start": _iso(row.get("start_ts") or row.get("start")),
                "end": _iso(row.get("end_ts") or row.get("end")),
                "center": _iso(row.get("center_ts") or row.get("center")),
                "cross_km": row.get("cross_km"),
                "alt_km": row.get("alt_km"),
                "color": row.get("color") or "#3DDCFF",
                "label": "possible coverage" if row.get("coverage") == "possible" else "systematic swath",
            }
        )
    return Snapshot(
        source=source,
        summary=summary,
        meta=meta,
        matches=[_row_match(row) for row in match_rows],
        tracks=tracks if isinstance(tracks, dict) else {"type": "FeatureCollection", "features": []},
        preview=_bytes(scene.get("preview_png")),
        passes=passes,
        pings=pings,
        refreshed_at=_iso(scene.get("refreshed_at")) or None,
    )


def _try_tiger() -> Snapshot | None:
    url = config.tiger_database_url()
    if not url:
        return None
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(url, connect_timeout=8, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT scene_id, acquired_at, platform, orbit_state,
                       bbox_west, bbox_south, bbox_east, bbox_north,
                       preview_png, summary_json, tracks_json, refreshed_at
                FROM scenes
                ORDER BY refreshed_at DESC
                LIMIT 1
                """
            )
            scene = cur.fetchone()
            if not scene:
                return None
            scene_id = scene["scene_id"]
            cur.execute("SELECT * FROM matches WHERE scene_id = %s", (scene_id,))
            matches = cur.fetchall()
            cur.execute("SELECT * FROM passes WHERE scene_id = %s", (scene_id,))
            passes = cur.fetchall()
            cur.execute(
                "SELECT scene_id, mmsi, ts, lat, lon, sog, name, length FROM ais_pings WHERE scene_id = %s",
                (scene_id,),
            )
            pings = cur.fetchall()
    return _snapshot_from_rows("tiger", scene, matches, passes, pings)


def _warehouse_cursor():
    if not (config.databricks_warehouse_id() and config.databricks_host()):
        return None
    from databricks.sdk.core import Config

    from databricks import sql

    cfg = Config()
    host = cfg.host.replace("https://", "").replace("http://", "").strip("/")
    warehouse_id = config.databricks_warehouse_id()
    return sql.connect(
        server_hostname=host,
        http_path=f"/sql/1.0/warehouses/{warehouse_id}",
        credentials_provider=lambda: cfg.authenticate,
    )


def _try_warehouse() -> Snapshot | None:
    conn = _warehouse_cursor()
    if conn is None:
        return None
    catalog, schema = catalog_name(), schema_name()
    table = f"{catalog}.{schema}"
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT scene_id, acquired_at, platform, orbit_state,
                       bbox_west, bbox_south, bbox_east, bbox_north,
                       preview_png, summary_json, tracks_json, refreshed_at
                FROM {table}.scenes
                ORDER BY refreshed_at DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            scene = dict(zip(cols, row, strict=False))
            scene_id = scene["scene_id"]

            def fetch(sql_text: str) -> list[dict]:
                cur.execute(sql_text, {"scene_id": scene_id})
                names = [d[0] for d in cur.description]
                return [dict(zip(names, item, strict=False)) for item in cur.fetchall()]

            matches = fetch(f"SELECT * FROM {table}.matches WHERE scene_id = %(scene_id)s")
            passes = fetch(f"SELECT * FROM {table}.passes WHERE scene_id = %(scene_id)s")
            pings = fetch(
                "SELECT scene_id, mmsi, ts, lat, lon, sog, name, length "
                f"FROM {table}.ais_pings WHERE scene_id = %(scene_id)s"
            )
    finally:
        conn.close()
    return _snapshot_from_rows("warehouse", scene, matches, passes, pings)


def get_snapshot(force: bool = False) -> Snapshot:
    global _cache, _cache_at
    now = time.time()
    if not force and _cache is not None and (now - _cache_at) < _TTL_S:
        return _cache
    snap = None
    for loader in (_try_tiger, _try_warehouse):
        try:
            snap = loader()
        except Exception as exc:
            logger.warning("live source %s failed: %s", loader.__name__, exc)
            snap = None
        if snap is not None:
            break
    if snap is None:
        snap = load_bundle()
    _cache = snap
    _cache_at = now
    return snap


def _as_pass(row: dict) -> Pass:
    return Pass(
        norad=int(row["norad"]),
        name=row.get("name") or "",
        family=row.get("family") or "",
        coverage=row.get("coverage") or "systematic",
        start=parse_time(row["start"]),
        end=parse_time(row["end"]),
        center=parse_time(row["center"]),
        cross_km=float(row.get("cross_km") or 0),
        alt_km=float(row.get("alt_km") or 0),
        color=row.get("color") or "#3DDCFF",
    )


def report_from_stored(passes: list[dict], window_kind: str, t0: datetime, t1: datetime, families: list[str] | None) -> dict | None:
    """Rebuild gap durations from stored pass windows. Durations are not stored."""
    selected = [row for row in passes if row.get("window_kind") == window_kind]
    if not selected:
        return None
    family_set = set(families or [])
    objects = [_as_pass(row) for row in selected]
    systematic = [p for p in objects if p.coverage == "systematic" and (not family_set or p.family in family_set)]
    possible = [p for p in objects if p.coverage == "possible"]
    gaps = coverage_gaps(systematic, t0, t1)
    long = longest_gap(gaps)
    optimistic = coverage_gaps(objects, t0, t1)
    opt_long = longest_gap(optimistic)
    return {
        "lat": None,
        "lon": None,
        "start": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": t1.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hours": (t1 - t0).total_seconds() / 3600.0,
        "source": "stored-passes",
        "gap_families": list(family_set) or None,
        "systematic_pass_count": len(systematic),
        "possible_pass_count": len(possible),
        "passes": [p.to_dict() for p in objects],
        "gaps": [g.to_dict() for g in gaps],
        "longest_gap": long.to_dict() if long else None,
        "longest_gap_if_all_tasked": opt_long.to_dict() if opt_long else None,
        "note": "Gaps recomputed from pass windows stored by darkwatch_refresh.",
    }


def ping_tracks(pings: list[Fix]) -> dict[str, list[Fix]]:
    grouped: dict[str, list[Fix]] = {}
    for fix in pings:
        grouped.setdefault(fix.mmsi, []).append(fix)
    return grouped


def traffic_query(lat: float, lon: float, radius_km: float, t0: datetime, t1: datetime, limit: int = 40) -> dict | None:
    """AIS counts from Tiger or the warehouse. None means the caller should use the local store."""
    snap = get_snapshot()
    if snap.source == "bundle":
        return None
    if not snap.pings:
        return {"source": snap.source, "vessels": [], "buckets": []}
    import math

    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * max(0.2, math.cos(math.radians(lat))))
    grouped: dict[str, dict] = {}
    buckets: dict[str, dict] = {}
    for fix in snap.pings:
        if not (t0 <= fix.t < t1):
            continue
        if not (lat - dlat <= fix.lat <= lat + dlat and lon - dlon <= fix.lon <= lon + dlon):
            continue
        row = grouped.setdefault(
            fix.mmsi,
            {"mmsi": fix.mmsi, "name": fix.name or "Unknown", "pings": 0, "start": fix.t, "end": fix.t},
        )
        row["pings"] += 1
        row["start"] = min(row["start"], fix.t)
        row["end"] = max(row["end"], fix.t)
        if fix.name:
            row["name"] = fix.name
        bucket = fix.t.replace(minute=(fix.t.minute // 5) * 5, second=0, microsecond=0)
        key = bucket.strftime("%Y-%m-%dT%H:%M:%SZ")
        slot = buckets.setdefault(key, {"bucket": key, "pings": 0, "vessels": set()})
        slot["pings"] += 1
        slot["vessels"].add(fix.mmsi)
    vessels = sorted(grouped.values(), key=lambda item: item["pings"], reverse=True)[:limit]
    for item in vessels:
        item["start"] = item["start"].strftime("%Y-%m-%dT%H:%M:%SZ")
        item["end"] = item["end"].strftime("%Y-%m-%dT%H:%M:%SZ")
    series = [
        {"bucket": key, "pings": buckets[key]["pings"], "vessels": len(buckets[key]["vessels"])}
        for key in sorted(buckets)
    ]
    return {"source": snap.source, "vessels": vessels, "buckets": series}
