"""Tiger Data / TimescaleDB store. Hypertable and a 5-minute continuous aggregate when available."""

from __future__ import annotations

from nimbus.storage import Store, ais_csv, box


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
        s, n, w, e = box(lat, lon, radius_km)
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
        s, n, w, e = box(lat, lon, radius_km)
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
