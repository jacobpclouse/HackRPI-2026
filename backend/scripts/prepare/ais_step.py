"""Download a Danish AIS day zip into data/raw/, filter it, write the sample."""

from __future__ import annotations

import csv
import gzip
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from darkwatch.detection.matching import Fix
from prepare import Target, log


def _parse_ais_time(text: str) -> datetime | None:
    text = text.strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def filter_ais(target: Target, zip_path: Path, force: bool = False) -> Path:
    dest = target.out_dir / "ais_pings.csv.gz"
    if not force and dest.exists() and dest.stat().st_size > 1000:
        log(f"AIS sample already present ({dest.stat().st_size} bytes)")
        return dest
    if not zip_path.exists():
        import httpx

        log(f"downloading AIS zip from {target.ais_url}")
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", target.ais_url, timeout=None, follow_redirects=True) as response:
            response.raise_for_status()
            with zip_path.open("wb") as handle:
                for chunk in response.iter_bytes(1 << 20):
                    handle.write(chunk)
    west, south, east, north = target.bbox
    buf = (west - 0.35, south - 0.35, east + 0.35, north + 0.35)
    dense_start = target.scene_time - timedelta(minutes=20)
    dense_end = target.scene_time + timedelta(minutes=20)
    names: dict[str, str] = {}
    lengths: dict[str, str] = {}
    last: dict[str, datetime] = {}
    kept: list[tuple] = []
    log(f"streaming {zip_path}")
    with zipfile.ZipFile(zip_path) as archive:
        name = archive.namelist()[0]
        with archive.open(name) as raw:
            text = (line.decode("utf-8", "replace") for line in raw)
            reader = csv.reader(text)
            header = next(reader)
            idx = {col.strip().lstrip("#").strip(): i for i, col in enumerate(header)}

            def col(row, *keys, default=""):
                for key in keys:
                    i = idx.get(key)
                    if i is not None and i < len(row):
                        return row[i].strip()
                return default

            n = 0
            for row in reader:
                n += 1
                if n % 2_000_000 == 0:
                    log(f"  {n/1e6:.0f}M rows, kept {len(kept)}")
                try:
                    lat = float(col(row, "Latitude"))
                    lon = float(col(row, "Longitude"))
                except ValueError:
                    continue
                if not (buf[1] <= lat <= buf[3] and buf[0] <= lon <= buf[2]):
                    continue
                mmsi = col(row, "MMSI")
                if not mmsi or mmsi == "Unknown":
                    continue
                when = _parse_ais_time(col(row, "Timestamp"))
                if when is None:
                    continue
                ship = col(row, "Name")
                if ship and ship.lower() != "unknown":
                    names[mmsi] = ship
                length = col(row, "Length")
                if length and length.lower() != "unknown":
                    lengths[mmsi] = length
                in_scene = south <= lat <= north and west <= lon <= east
                dense = in_scene and dense_start <= when <= dense_end
                minimum = 8 if dense else 120
                prev = last.get(mmsi)
                if prev is not None and (when - prev).total_seconds() < minimum:
                    continue
                last[mmsi] = when
                sog = col(row, "SOG")
                kept.append((when, mmsi, lat, lon, sog))
    kept.sort(key=lambda item: (item[1], item[0]))
    log(f"kept {len(kept)} pings from {len(names)} named vessels (names seen {len(names)})")
    target.out_dir.mkdir(parents=True, exist_ok=True)
    with gzip.open(dest, "wt", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ts", "mmsi", "lat", "lon", "sog", "name", "length"])
        for when, mmsi, lat, lon, sog in kept:
            writer.writerow(
                [
                    when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    mmsi,
                    f"{lat:.5f}",
                    f"{lon:.5f}",
                    sog,
                    names.get(mmsi, ""),
                    lengths.get(mmsi, ""),
                ]
            )
    return dest


def load_tracks(path: Path) -> dict[str, list[Fix]]:
    tracks: dict[str, list[Fix]] = {}
    with gzip.open(path, "rt") as handle:
        for row in csv.DictReader(handle):
            try:
                sog = float(row["sog"]) if row["sog"] else None
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
    return tracks


def tracks_geojson(tracks: dict[str, list[Fix]], bbox: tuple[float, float, float, float]) -> dict:
    west, south, east, north = bbox
    features = []
    for mmsi, fixes in tracks.items():
        ordered = sorted(fixes, key=lambda f: f.t)
        inside = [f for f in ordered if south <= f.lat <= north and west <= f.lon <= east]
        if len(inside) < 2:
            continue
        thinned = [inside[0]]
        for fix in inside[1:]:
            if (fix.t - thinned[-1].t).total_seconds() >= 180:
                thinned.append(fix)
        if thinned[-1] is not inside[-1]:
            thinned.append(inside[-1])
        name = next((f.name for f in reversed(ordered) if f.name), "")
        features.append(
            {
                "type": "Feature",
                "properties": {"mmsi": mmsi, "name": name or "Unknown", "pings": len(thinned)},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[round(f.lon, 5), round(f.lat, 5)] for f in thinned],
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def run(target: Target, *, zip_path: Path | None = None, force: bool = False) -> Path:
    path = filter_ais(target, zip_path or target.ais_zip_path(), force)
    tracks = load_tracks(path)
    geo = tracks_geojson(tracks, target.bbox)
    (target.out_dir / "ais_tracks.geojson").write_text(json.dumps(geo))
    log(f"display tracks: {len(geo['features'])}")
    return path
