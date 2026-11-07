"""Local DuckDB store: the default when TIGER_DATABASE_URL is unset or unreachable."""

from __future__ import annotations

import json
from pathlib import Path

from darkwatch.storage import Store, ais_csv, box, duck_path, matches_json


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
        s, n, w, e = box(lat, lon, radius_km)
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
        s, n, w, e = box(lat, lon, radius_km)
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
