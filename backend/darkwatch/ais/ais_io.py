"""Read the filtered Danish AIS sample."""

from __future__ import annotations

import csv
import gzip
from datetime import datetime
from pathlib import Path

from darkwatch import paths
from darkwatch.detection.matching import Fix


def ais_csv_path() -> Path:
    return paths.demo_dir() / "ais_pings.csv.gz"


_tracks: dict[str, list[Fix]] | None = None


def load_tracks(path: Path | None = None) -> dict[str, list[Fix]]:
    global _tracks
    if path is None and _tracks is not None:
        return _tracks
    src = path or ais_csv_path()
    tracks: dict[str, list[Fix]] = {}
    if not src.exists():
        return tracks
    with gzip.open(src, "rt") as handle:
        for row in csv.DictReader(handle):
            try:
                sog = float(row["sog"]) if row.get("sog") else None
            except ValueError:
                sog = None
            fix = Fix(
                mmsi=row["mmsi"],
                t=datetime.fromisoformat(row["ts"].replace("Z", "+00:00")),
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                name=row.get("name") or "",
                sog=sog,
            )
            tracks.setdefault(fix.mmsi, []).append(fix)
    if path is None:
        _tracks = tracks
    return tracks
