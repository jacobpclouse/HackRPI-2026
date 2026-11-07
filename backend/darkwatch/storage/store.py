"""AIS and detection storage.

TIGER_DATABASE_URL, when set, is a Tiger Data / TimescaleDB Postgres URL.
Hypertables and a 5-minute continuous aggregate are created when the
extension is present. Any connection or extension failure falls back to a
local DuckDB file so the demo still answers "who was near here".
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from darkwatch import config, paths


def duck_path() -> Path:
    return paths.cache_dir() / "darkwatch.duckdb"


def ais_csv() -> Path:
    return paths.demo_dir() / "ais_pings.csv.gz"


def matches_json() -> Path:
    return paths.demo_dir() / "matches.json"


class Store:
    kind = "none"

    def ready(self) -> bool:
        return False

    def vessels_between(self, lat, lon, radius_km, t0, t1, limit=40):
        return []

    def buckets(self, lat, lon, radius_km, t0, t1):
        return []

    def status(self) -> dict:
        return {"kind": self.kind, "ready": self.ready()}


def _box(lat, lon, radius_km):
    import math

    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * max(0.2, math.cos(math.radians(lat))))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


class DuckStore(Store):
    kind = "duckdb"

    def __init__(self, path: Path | None = None):
        import duckdb

        path = path or duck_path()
        self.path = path

        path.parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(path))
        self.con.execute(
            """
            CREATE TABLE IF NOT EXISTS ais_pings (
                mmsi VARCHAR, ts TIMESTAMP, lat DOUBLE, lon DOUBLE,
                sog DOUBLE, name VARCHAR
            )
            """
        )
        self.con.execute(
            """
            CREATE TABLE IF NOT EXISTS detections (
                det_id VARCHAR, lat DOUBLE, lon DOUBLE, matched BOOLEAN,
                confidence DOUBLE, peak_db DOUBLE, shore_km DOUBLE,
                nearest_ais_km DOUBLE, mmsi VARCHAR
            )
            """
        )
        n = self.con.execute("SELECT count(*) FROM ais_pings").fetchone()[0]
        if n == 0 and ais_csv().exists():
            self.con.execute(
                """
                INSERT INTO ais_pings
                SELECT mmsi, ts::TIMESTAMP, lat, lon,
                       TRY_CAST(sog AS DOUBLE), name
                FROM read_csv_auto(?, header=true)
                """,
                [str(ais_csv())],
            )
        d = self.con.execute("SELECT count(*) FROM detections").fetchone()[0]
        if d == 0 and matches_json().exists():
            import json

            rows = json.loads(matches_json().read_text())
            if rows:
                self.con.executemany(
                    """
                    INSERT INTO detections VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    [
                        (
                            r["id"],
                            r["lat"],
                            r["lon"],
                            bool(r["matched"]),
                            r.get("confidence"),
                            r.get("peak_db"),
                            r.get("shore_km"),
                            r.get("nearest_ais_km"),
                            r.get("mmsi"),
                        )
                        for r in rows
                    ],
                )
        self._count = self.con.execute("SELECT count(*) FROM ais_pings").fetchone()[0]

    def ready(self) -> bool:
        return self._count > 0

    def vessels_between(self, lat, lon, radius_km, t0, t1, limit=40):
        s, n, w, e = _box(lat, lon, radius_km)
        rows = self.con.execute(
            """
            SELECT mmsi, any_value(name) AS name, count(*) AS pings,
                   min(ts) AS t0, max(ts) AS t1
            FROM ais_pings
            WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?
              AND ts >= ? AND ts < ?
            GROUP BY mmsi
            ORDER BY pings DESC
            LIMIT ?
            """,
            [s, n, w, e, t0.replace(tzinfo=None), t1.replace(tzinfo=None), limit],
        ).fetchall()
        return [
            {
                "mmsi": r[0],
                "name": r[1] or "Unknown",
                "pings": int(r[2]),
                "start": r[3].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": r[4].strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            for r in rows
        ]

    def buckets(self, lat, lon, radius_km, t0, t1):
        s, n, w, e = _box(lat, lon, radius_km)
        rows = self.con.execute(
            """
            SELECT time_bucket(INTERVAL '5 minutes', ts) AS bucket,
                   count(*) AS pings,
                   count(DISTINCT mmsi) AS vessels
            FROM ais_pings
            WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?
              AND ts >= ? AND ts < ?
            GROUP BY 1
            ORDER BY 1
            """,
            [s, n, w, e, t0.replace(tzinfo=None), t1.replace(tzinfo=None)],
        ).fetchall()
        return [
            {"bucket": r[0].strftime("%Y-%m-%dT%H:%M:%SZ"), "pings": int(r[1]), "vessels": int(r[2])}
            for r in rows
        ]

    def status(self) -> dict:
        return {"kind": self.kind, "ready": self.ready(), "ais_pings": self._count, "path": str(self.path)}


class TigerStore(Store):
    kind = "timescale"

    def __init__(self, url: str):
        import psycopg

        self.url = url
        self.conn = psycopg.connect(url, connect_timeout=8)
        self.conn.autocommit = True
        self._hypertable = False
        with self.conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ais_pings (
                    mmsi text,
                    ts timestamptz NOT NULL,
                    lat double precision,
                    lon double precision,
                    sog double precision,
                    name text
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS detections (
                    det_id text,
                    lat double precision,
                    lon double precision,
                    matched boolean,
                    confidence double precision,
                    peak_db double precision,
                    shore_km double precision,
                    nearest_ais_km double precision,
                    mmsi text,
                    ts timestamptz
                )
                """
            )
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
                cur.execute(
                    "SELECT create_hypertable('ais_pings', 'ts', if_not_exists => TRUE)"
                )
                self._hypertable = True
                cur.execute(
                    """
                    CREATE MATERIALIZED VIEW IF NOT EXISTS ais_pings_5min
                    WITH (timescaledb.continuous) AS
                    SELECT time_bucket('5 minutes', ts) AS bucket,
                           count(*) AS pings,
                           count(DISTINCT mmsi) AS vessels
                    FROM ais_pings
                    GROUP BY bucket
                    WITH NO DATA
                    """
                )
            except Exception:
                self.conn.rollback() if not self.conn.autocommit else None
                self._hypertable = False
        self._load_if_empty()

    def _load_if_empty(self) -> None:
        import csv
        import gzip

        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM ais_pings")
            n = cur.fetchone()[0]
        if n or not ais_csv().exists():
            self._count = n
            return
        rows = []
        with gzip.open(ais_csv(), "rt") as handle:
            for row in csv.DictReader(handle):
                sog = row["sog"]
                try:
                    sog_v = float(sog) if sog else None
                except ValueError:
                    sog_v = None
                rows.append((row["mmsi"], row["ts"], float(row["lat"]), float(row["lon"]), sog_v, row["name"]))
                if len(rows) >= 5000:
                    self._insert(rows)
                    rows = []
        if rows:
            self._insert(rows)
        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM ais_pings")
            self._count = cur.fetchone()[0]

    def _insert(self, rows) -> None:
        with self.conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO ais_pings (mmsi, ts, lat, lon, sog, name) VALUES (%s,%s,%s,%s,%s,%s)",
                rows,
            )

    def ready(self) -> bool:
        return getattr(self, "_count", 0) > 0

    def vessels_between(self, lat, lon, radius_km, t0, t1, limit=40):
        s, n, w, e = _box(lat, lon, radius_km)
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT mmsi, max(name), count(*), min(ts), max(ts)
                FROM ais_pings
                WHERE lat BETWEEN %s AND %s AND lon BETWEEN %s AND %s
                  AND ts >= %s AND ts < %s
                GROUP BY mmsi
                ORDER BY count(*) DESC
                LIMIT %s
                """,
                (s, n, w, e, t0, t1, limit),
            )
            rows = cur.fetchall()
        return [
            {
                "mmsi": r[0],
                "name": r[1] or "Unknown",
                "pings": int(r[2]),
                "start": r[3].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": r[4].strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            for r in rows
        ]

    def buckets(self, lat, lon, radius_km, t0, t1):
        s, n, w, e = _box(lat, lon, radius_km)
        sql = (
            """
            SELECT time_bucket('5 minutes', ts) AS bucket,
                   count(*) AS pings,
                   count(DISTINCT mmsi) AS vessels
            FROM ais_pings
            WHERE lat BETWEEN %s AND %s AND lon BETWEEN %s AND %s
              AND ts >= %s AND ts < %s
            GROUP BY 1
            ORDER BY 1
            """
            if self._hypertable
            else """
            SELECT to_timestamp(floor(extract(epoch FROM ts) / 300) * 300) AS bucket,
                   count(*) AS pings,
                   count(DISTINCT mmsi) AS vessels
            FROM ais_pings
            WHERE lat BETWEEN %s AND %s AND lon BETWEEN %s AND %s
              AND ts >= %s AND ts < %s
            GROUP BY 1
            ORDER BY 1
            """
        )
        with self.conn.cursor() as cur:
            cur.execute(sql, (s, n, w, e, t0, t1))
            rows = cur.fetchall()
        return [
            {"bucket": r[0].strftime("%Y-%m-%dT%H:%M:%SZ"), "pings": int(r[1]), "vessels": int(r[2])}
            for r in rows
        ]

    def status(self) -> dict:
        return {
            "kind": "timescaledb" if self._hypertable else "postgres",
            "ready": self.ready(),
            "hypertable": self._hypertable,
            "ais_pings": getattr(self, "_count", 0),
        }


def open_store() -> Store:
    url = config.tiger_database_url()
    if url:
        try:
            return TigerStore(url)
        except Exception as exc:
            duck = DuckStore()
            duck.fallback_reason = str(exc)
            return duck
    if ais_csv().exists():
        try:
            return DuckStore()
        except Exception:
            return Store()
    return Store()


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
