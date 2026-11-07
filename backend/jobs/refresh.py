#!/usr/bin/env python3
"""Serverless refresh for DarkWatch.

Finds the repo from ``sys.argv[0]`` / cwd / ``--repo-root`` because a
serverless ``spark_python_task`` has no ``__file__``. Downloads the newest
Sentinel-1 RTC scene over the Kattegat chip that has a Danish AIS day file,
runs CFAR and AIS matching, predicts passes, and writes Delta tables. If the
``darkwatch`` / ``tiger_url`` secret can be read, the same rows go to Tiger.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("darkwatch.jobs")


def _bootstrap(argv0: str, repo_root_arg: str | None):
    """Put backend/ on sys.path. The package is not importable until then."""
    cwd = Path.cwd()
    candidates = []
    # Read directly: darkwatch.config is not importable yet.
    if os.environ.get("DARKWATCH_ROOT"):
        candidates.append(Path(os.environ["DARKWATCH_ROOT"]))
    if repo_root_arg:
        candidates.append(Path(repo_root_arg))
    if argv0:
        script = Path(argv0)
        if not script.is_absolute():
            script = cwd / script
        candidates.extend(script.resolve().parents)
    candidates.extend([cwd, *cwd.parents])
    backend = None
    for candidate in candidates:
        if (candidate / "backend" / "darkwatch" / "paths.py").is_file():
            backend = candidate / "backend"
            break
    if backend is None:
        raise SystemExit(
            "Cannot locate DarkWatch. Pass --repo-root or run from the bundle files directory. "
            f"argv0={argv0!r} cwd={cwd}"
        )
    for path in (backend, backend / "scripts"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from darkwatch.paths import repo_root

    return repo_root(argv0=argv0, cwd=cwd, extra=repo_root_arg)


def _search_scene(bbox: tuple[float, float, float, float]) -> dict:
    import httpx

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=21)
    response = httpx.post(
        "https://planetarycomputer.microsoft.com/api/stac/v1/search",
        json={
            "collections": ["sentinel-1-rtc"],
            "bbox": list(bbox),
            "datetime": f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "limit": 30,
            "query": {"sar:instrument_mode": {"eq": "IW"}},
        },
        timeout=60,
    )
    response.raise_for_status()
    features = response.json().get("features") or []
    features.sort(key=lambda item: item["properties"].get("datetime") or "", reverse=True)
    from shapely.geometry import box, shape
    region_geometry = box(*bbox)
    for feature in features:
        # Reject adjacent scene slivers: a bbox intersection alone is insufficient.
        if shape(feature["geometry"]).intersection(region_geometry).area / region_geometry.area < 0.8:
            continue
        acquired = feature["properties"]["datetime"][:10]
        url = f"http://aisdata.ais.dk.s3.eu-central-1.amazonaws.com/aisdk-{acquired}.zip"
        head = httpx.head(url, timeout=30, follow_redirects=True)
        if head.status_code == 200:
            feature["_ais_url"] = url
            feature["_ais_day"] = acquired
            return feature
    raise SystemExit("No Sentinel-1 RTC scene in the last 21 days has a Danish AIS zip yet.")


def _pass_rows(scene_id: str, summary: dict, refreshed: str) -> list[dict]:
    from darkwatch.detection import coverage_report
    from darkwatch.orbit import parse_time

    west, south, east, north = summary["bbox"]
    lat = (south + north) / 2
    lon = (west + east) / 2
    scene_time = parse_time(summary["scene_time"])
    day0 = scene_time.replace(hour=0, minute=0, second=0, microsecond=0)
    windows = {
        "scene_day": coverage_report(lat, lon, day0, 24),
        "upcoming": coverage_report(lat, lon, datetime.now(timezone.utc).replace(second=0, microsecond=0), 48),
    }
    rows = []
    for kind, report in windows.items():
        for item in report["passes"]:
            rows.append(
                {
                    "scene_id": scene_id,
                    "window_kind": kind,
                    "norad": int(item["norad"]),
                    "name": item["name"],
                    "family": item["family"],
                    "coverage": item["coverage"],
                    "start_ts": item["start"],
                    "end_ts": item["end"],
                    "center_ts": item["center"],
                    "cross_km": float(item["cross_km"]),
                    "alt_km": float(item["alt_km"]),
                    "color": item.get("color") or "",
                    "refreshed_at": refreshed,
                }
            )
    return rows


def _write_delta(spark, catalog: str, schema: str, frames: dict) -> None:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
    for name, rows in frames.items():
        # Matching distances/confidence may be null for every detection.
        match_schema = (
            "scene_id STRING, det_id STRING, lat DOUBLE, lon DOUBLE, pixels BIGINT, "
            "peak_db DOUBLE, shore_km DOUBLE, matched BOOLEAN, mmsi STRING, name STRING, "
            "match_km DOUBLE, nearest_ais_km DOUBLE, nearest_mmsi STRING, nearest_name STRING, "
            "confidence DOUBLE, in_mpa BOOLEAN, near_mpa BOOLEAN, mpa_name STRING, mpa_km DOUBLE"
        )
        frame = spark.createDataFrame(rows, schema=match_schema if name == "matches" else None)
        (
            frame.write.mode("overwrite")
            .option("overwriteSchema", "true")
            .saveAsTable(f"{catalog}.{schema}.{name}")
        )
        logger.info(f"wrote {catalog}.{schema}.{name} ({len(rows)} rows)")


def _write_tiger(url: str, frames: dict) -> None:
    import psycopg

    ddl = [
        """
        CREATE TABLE IF NOT EXISTS scenes (
            scene_id text, acquired_at text, platform text, orbit_state text,
            bbox_west double precision, bbox_south double precision,
            bbox_east double precision, bbox_north double precision,
            preview_png bytea, summary_json text, tracks_json text, refreshed_at text
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS detections (
            scene_id text, det_id text, lat double precision, lon double precision,
            pixels int, peak_db double precision, shore_km double precision
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS matches (
            scene_id text, det_id text, lat double precision, lon double precision,
            pixels int, peak_db double precision, shore_km double precision,
            matched boolean, mmsi text, name text, match_km double precision,
            nearest_ais_km double precision, nearest_mmsi text, nearest_name text,
            confidence double precision, in_mpa boolean, near_mpa boolean,
            mpa_name text, mpa_km double precision
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ais_pings (
            scene_id text, mmsi text, ts timestamptz NOT NULL,
            lat double precision, lon double precision, sog double precision,
            name text, length text
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS passes (
            scene_id text, window_kind text, norad int, name text, family text,
            coverage text, start_ts timestamptz, end_ts timestamptz, center_ts timestamptz,
            cross_km double precision, alt_km double precision, color text, refreshed_at text
        )
        """,
    ]
    with psycopg.connect(url, connect_timeout=15) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            for statement in ddl:
                cur.execute(statement)
            # The app's traffic store may have bootstrapped these two tables.
            cur.execute("ALTER TABLE ais_pings ADD COLUMN IF NOT EXISTS scene_id text, ADD COLUMN IF NOT EXISTS length text")
            cur.execute("ALTER TABLE detections ADD COLUMN IF NOT EXISTS scene_id text, ADD COLUMN IF NOT EXISTS pixels int")
            try:
                cur.execute("SELECT create_hypertable('ais_pings', 'ts', if_not_exists => TRUE)")
            except Exception as exc:
                logger.info(f"ais_pings hypertable skipped: {exc}")
            try:
                cur.execute("SELECT create_hypertable('passes', 'center_ts', if_not_exists => TRUE)")
            except Exception as exc:
                logger.info(f"passes hypertable skipped: {exc}")
            for table in ("scenes", "detections", "matches", "ais_pings", "passes"):
                cur.execute(f"TRUNCATE {table}")
            _insert(cur, "scenes", frames["scenes"])
            _insert(cur, "detections", frames["detections"])
            _insert(cur, "matches", frames["matches"])
            _insert(cur, "ais_pings", frames["ais_pings"])
            _insert(cur, "passes", frames["passes"])
    logger.info("wrote Tiger tables")


def _insert(cur, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})"
    batch = []
    for row in rows:
        batch.append(tuple(row[column] for column in columns))
        if len(batch) >= 2000:
            cur.executemany(sql, batch)
            batch = []
    if batch:
        cur.executemany(sql, batch)


def _tiger_url(spark) -> str:
    try:
        from pyspark.dbutils import DBUtils

        return DBUtils(spark).secrets.get(scope="darkwatch", key="tiger_url") or ""
    except Exception as exc:
        logger.warning(f"tiger_url secret not used: {exc}")
        return ""


def run(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="workspace")
    parser.add_argument("--schema", default="darkwatch")
    parser.add_argument("--repo-root", default="")
    parser.add_argument("--check", action="store_true", help="Resolve the repo root and exit.")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    root = _bootstrap(sys.argv[0], args.repo_root or None)
    logger.info(f"repo root {root}")
    if args.check:
        logger.info("check ok: spark not required")
        logger.info(f"tables {args.catalog}.{args.schema}.{{scenes,detections,matches,ais_pings,passes}}")
        return

    # Load libpq before GDAL/rasterio to avoid bundled native-library collisions.

    import prepare_demo as prep
    from pyspark.sql import SparkSession

    from darkwatch.geo import by_id

    spark = SparkSession.builder.getOrCreate()
    region = by_id("kattegat")
    bbox = tuple(region["bbox"])
    feature = _search_scene(bbox)
    acquired = datetime.fromisoformat(feature["properties"]["datetime"].replace("Z", "+00:00"))
    work = Path("/tmp/darkwatch-refresh")
    work.mkdir(parents=True, exist_ok=True)
    bundled_mpa = root / "data" / "demo" / "mpas.geojson"
    if bundled_mpa.exists() and not (work / "mpas.geojson").exists():
        (work / "mpas.geojson").write_bytes(bundled_mpa.read_bytes())

    prep.DEMO = work
    prep.BBOX = bbox
    prep.SCENE_ID = feature["id"]
    prep.SCENE_TIME = acquired.replace(microsecond=0)
    prep.AIS_URL = feature["_ais_url"]
    logger.info(f"scene {prep.SCENE_ID} ais {prep.AIS_URL}")

    meta = prep.clip_scene(force=True)
    detections = prep.run_cfar(meta, force=True)
    ais_zip = Path("/tmp/darkwatch-raw") / f"aisdk-{feature['_ais_day']}.zip"
    ais_zip.parent.mkdir(parents=True, exist_ok=True)
    ais_path = prep.filter_ais(ais_zip, force=True)
    tracks = prep.load_tracks(ais_path)
    (work / "ais_tracks.geojson").write_text(json.dumps(prep.tracks_geojson(tracks)))
    mpas = json.loads((work / "mpas.geojson").read_text()) if (work / "mpas.geojson").exists() else {"features": []}
    try:
        from darkwatch.geo import fetch_natura2000, simplify_collection

        west, south, east, north = bbox
        fresh = simplify_collection(fetch_natura2000((west - 0.4, south - 0.4, east + 0.4, north + 0.4)))
        if fresh.get("features"):
            mpas = fresh
            (work / "mpas.geojson").write_text(json.dumps(fresh))
    except Exception as exc:
        logger.warning(f"MPA refresh skipped: {exc}")
    result = prep.match_all(detections, tracks, mpas)
    (work / "matches.json").write_text(json.dumps(result["detections"]))
    (work / "summary.json").write_text(json.dumps(result["summary"]))
    summary = result["summary"]
    refreshed = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    scene_id = summary["scene_id"]
    west, south, east, north = summary["bbox"]
    scenes = [
        {
            "scene_id": scene_id,
            "acquired_at": summary["scene_time"],
            "platform": meta.get("platform") or "",
            "orbit_state": meta.get("orbit_state") or "",
            "bbox_west": float(west),
            "bbox_south": float(south),
            "bbox_east": float(east),
            "bbox_north": float(north),
            "preview_png": bytearray((work / "scene_preview.png").read_bytes()),
            "summary_json": json.dumps(summary),
            "tracks_json": (work / "ais_tracks.geojson").read_text(),
            "refreshed_at": refreshed,
        }
    ]
    det_rows = [
        {
            "scene_id": scene_id,
            "det_id": row["id"],
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "pixels": int(row["pixels"]),
            "peak_db": float(row["peak_db"]),
            "shore_km": float(row["shore_km"]),
        }
        for row in detections
    ]
    match_rows = []
    for row in result["detections"]:
        match_rows.append(
            {
                "scene_id": scene_id,
                "det_id": row["id"],
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "pixels": int(row["pixels"]),
                "peak_db": float(row["peak_db"]),
                "shore_km": float(row["shore_km"]),
                "matched": bool(row["matched"]),
                "mmsi": row.get("mmsi") or "",
                "name": row.get("name") or "",
                "match_km": row.get("match_km"),
                "nearest_ais_km": row.get("nearest_ais_km"),
                "nearest_mmsi": row.get("nearest_mmsi") or "",
                "nearest_name": row.get("nearest_name") or "",
                "confidence": row.get("confidence"),
                "in_mpa": bool(row.get("in_mpa")),
                "near_mpa": bool(row.get("near_mpa")),
                "mpa_name": row.get("mpa_name") or "",
                "mpa_km": row.get("mpa_km"),
            }
        )
    import csv
    import gzip

    ping_rows = []
    with gzip.open(ais_path, "rt") as handle:
        for record in csv.DictReader(handle):
            sog = record.get("sog") or ""
            try:
                sog_v = float(sog) if sog else None
            except ValueError:
                sog_v = None
            ping_rows.append(
                {
                    "scene_id": scene_id,
                    "mmsi": record["mmsi"],
                    "ts": record["ts"],
                    "lat": float(record["lat"]),
                    "lon": float(record["lon"]),
                    "sog": sog_v,
                    "name": record.get("name") or "",
                    "length": record.get("length") or "",
                }
            )
    pass_rows = _pass_rows(scene_id, summary, refreshed)
    frames = {
        "scenes": scenes,
        "detections": det_rows,
        "matches": match_rows,
        "ais_pings": ping_rows,
        "passes": pass_rows,
    }
    _write_delta(spark, args.catalog, args.schema, frames)
    url = _tiger_url(spark)
    if url:
        try:
            def _pg(value: str) -> str:
                return value.replace("Z", "+00:00") if isinstance(value, str) else value

            tiger_frames = {
                "scenes": scenes,
                "detections": det_rows,
                "matches": match_rows,
                "ais_pings": [{**row, "ts": _pg(row["ts"])} for row in ping_rows],
                "passes": [
                    {**row, "start_ts": _pg(row["start_ts"]), "end_ts": _pg(row["end_ts"]), "center_ts": _pg(row["center_ts"])}
                    for row in pass_rows
                ],
            }
            _write_tiger(url, tiger_frames)
        except Exception as exc:
            logger.warning(f"Tiger write failed, Delta tables are still updated: {exc}")
    logger.info(
        f"done scene={scene_id} detections={summary.get('detections')} "
        f"matched={summary.get('matched')} unmatched={summary.get('unmatched')} "
        f"passes={len(pass_rows)}"
    )


if __name__ == "__main__":
    run()
