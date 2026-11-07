#!/usr/bin/env python3
"""Build the committed Kattegat demo: Sentinel-1 RTC chip, Danish AIS, CFAR, MPAs.

Re-runnable. Skips steps whose outputs already exist unless --force is passed.
The AIS zip is large (~550 MB); it is filtered and not committed.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import logging
import math
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from darkwatch import config, paths  # noqa: E402

config.configure_gdal()

from darkwatch.detection import CFARDetector, Fix, confidence_score, match_detections  # noqa: E402
from darkwatch.geo import annotate_mpa, fetch_natura2000, simplify_collection  # noqa: E402

logger = logging.getLogger("darkwatch.scripts")
DEMO = paths.demo_dir()
SCENE_ID = "S1D_IW_GRDH_1SDV_20261102T052330_20261102T052402_005284_00A0D2_rtc"
SCENE_TIME = datetime(2026, 11, 2, 5, 23, 46, tzinfo=timezone.utc)
BBOX = (11.45, 56.60, 12.30, 57.20)  # west, south, east, north
AIS_URL = "http://aisdata.ais.dk.s3.eu-central-1.amazonaws.com/aisdk-2026-11-02.zip"
NE_URL = "https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip"
RES_M = 30.0


def log(msg: str) -> None:
    logger.info(msg)


def sign_href(href: str) -> str:
    import httpx

    response = httpx.get(
        "https://planetarycomputer.microsoft.com/api/sas/v1/sign",
        params={"href": href},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["href"]


def fetch_stac_item() -> dict:
    import httpx

    response = httpx.post(
        "https://planetarycomputer.microsoft.com/api/stac/v1/search",
        json={"collections": ["sentinel-1-rtc"], "ids": [SCENE_ID], "limit": 1},
        timeout=60,
    )
    response.raise_for_status()
    features = response.json().get("features") or []
    if not features:
        raise SystemExit(f"STAC item not found: {SCENE_ID}")
    return features[0]


def clip_scene(force: bool) -> dict:
    meta_path = DEMO / "scene_meta.json"
    npz_path = DEMO / "scene_vv.npz"
    png_path = DEMO / "scene_preview.png"
    if not force and meta_path.exists() and npz_path.exists() and png_path.exists():
        log("scene chip already present")
        return json.loads(meta_path.read_text())

    import rasterio
    from PIL import Image
    from rasterio.enums import Resampling
    from rasterio.transform import Affine, from_bounds
    from rasterio.warp import reproject, transform_bounds
    from rasterio.windows import Window
    from rasterio.windows import from_bounds as window_from_bounds

    log("searching Planetary Computer for Sentinel-1 RTC")
    item = fetch_stac_item()
    props = item["properties"]
    href = item["assets"]["vv"]["href"]
    signed = sign_href(href)
    west, south, east, north = BBOX
    with rasterio.open("/vsicurl/" + signed) as src:
        log(f"opened {src.width}x{src.height} {src.crs} dtype={src.dtypes}")
        sb = transform_bounds("EPSG:4326", src.crs, west, south, east, north, densify_pts=21)
        window = window_from_bounds(*sb, transform=src.transform).intersection(
            Window(0, 0, src.width, src.height)
        )
        if window.width < 10 or window.height < 10:
            raise SystemExit(f"bbox missed the scene footprint: {window}")
        # Native RTC posting is about 10 m. Average down toward RES_M.
        scale = max(1.0, RES_M / 10.0)
        out_h = max(32, int(window.height / scale))
        out_w = max(32, int(window.width / scale))
        log(f"reading window {int(window.width)}x{int(window.height)} -> {out_w}x{out_h}")
        raw = src.read(
            1,
            window=window,
            out_shape=(out_h, out_w),
            resampling=Resampling.average,
            boundless=False,
        )
        win_transform = src.window_transform(window) * Affine.scale(
            window.width / out_w, window.height / out_h
        )
        src_crs = src.crs
        nodata = src.nodata

    raw = raw.astype(np.float32)
    invalid = ~np.isfinite(raw) | (raw < 0)
    if nodata is not None:
        invalid |= raw == np.float32(nodata)
    raw = np.where(invalid, -9999.0, raw)

    mean_lat = (south + north) / 2
    dst_w = max(32, int((east - west) * 111_320 * math.cos(math.radians(mean_lat)) / RES_M))
    dst_h = max(32, int((north - south) * 111_320 / RES_M))
    dst = np.full((dst_h, dst_w), -9999.0, dtype=np.float32)
    dst_transform = from_bounds(west, south, east, north, dst_w, dst_h)
    reproject(
        source=raw,
        destination=dst,
        src_transform=win_transform,
        src_crs=src_crs,
        src_nodata=-9999.0,
        dst_transform=dst_transform,
        dst_crs="EPSG:4326",
        dst_nodata=-9999.0,
        resampling=Resampling.bilinear,
    )
    dst = np.where(dst <= -1000, np.nan, dst)
    valid = np.isfinite(dst) & (dst > 0)
    frac = float(valid.mean())
    log(f"warped {dst_w}x{dst_h}, valid fraction {frac:.2f}, median {np.nanmedian(dst):.4f}")
    if frac < 0.4:
        log("warning: less than 40% of the chip has SAR pixels; the bbox may clip the footprint")

    # dB stretch for the preview, ocean-oriented.
    db = 10.0 * np.log10(np.clip(np.where(valid, dst, 1e-5), 1e-5, None))
    sample = db[valid]
    lo, hi = np.percentile(sample, [8, 99.2]) if sample.size else (-25, 0)
    scaled = np.clip((db - lo) / max(1e-3, hi - lo), 0, 1)
    gray = (np.where(valid, scaled, 0) * 255).astype(np.uint8)
    alpha = np.where(valid, 255, 0).astype(np.uint8)
    Image.fromarray(np.dstack([gray, gray, gray, alpha]), mode="RGBA").save(png_path)

    # float16 keeps the chip under the Databricks Apps 10 MB per-file limit.
    np.savez_compressed(npz_path, vv=np.nan_to_num(dst, nan=0).astype(np.float16))
    meta = {
        "scene_id": SCENE_ID,
        "collection": "sentinel-1-rtc",
        "platform": props.get("platform"),
        "datetime": props.get("datetime"),
        "start_datetime": props.get("start_datetime"),
        "end_datetime": props.get("end_datetime"),
        "orbit_state": props.get("sat:orbit_state"),
        "relative_orbit": props.get("sat:relative_orbit"),
        "bbox": [west, south, east, north],
        "width": int(dst_w),
        "height": int(dst_h),
        "crs": "EPSG:4326",
        "resolution_m": RES_M,
        "transform": [dst_transform.a, dst_transform.b, dst_transform.c, dst_transform.d, dst_transform.e, dst_transform.f],
        "valid_fraction": round(frac, 3),
        "vv_percentiles": {
            "p50": float(np.nanpercentile(dst, 50)),
            "p99": float(np.nanpercentile(dst, 99)),
        },
        "source": "Microsoft Planetary Computer sentinel-1-rtc, SAS-signed, no account",
        "asset": "vv",
        "preview": "scene_preview.png",
        "array": "scene_vv.npz",
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    log(f"wrote {png_path.name} and {npz_path.name}")
    return meta


def ensure_land_shp() -> Path:
    shp = Path("/tmp/darkwatch-ne/ne_10m_land.shp")
    if shp.exists():
        return shp
    import io
    import zipfile as zf

    import httpx

    log("downloading Natural Earth 10m land")
    response = httpx.get(NE_URL, timeout=120, follow_redirects=True)
    response.raise_for_status()
    dest = Path("/tmp/darkwatch-ne")
    dest.mkdir(parents=True, exist_ok=True)
    with zf.ZipFile(io.BytesIO(response.content)) as archive:
        archive.extractall(dest)
    return shp


def land_mask(meta: dict) -> np.ndarray:
    import shapefile
    from rasterio import features
    from rasterio.transform import Affine
    from shapely.geometry import box, shape

    west, south, east, north = meta["bbox"]
    transform = Affine(*meta["transform"])
    region = box(west, south, east, north)
    reader = shapefile.Reader(str(ensure_land_shp()))
    geoms = []
    for shp in reader.shapes():
        geom = shape(shp.__geo_interface__)
        if not geom.intersects(region):
            continue
        piece = geom.intersection(region)
        if not piece.is_empty:
            geoms.append(piece)
    if not geoms:
        return np.zeros((meta["height"], meta["width"]), dtype=bool)
    mask = features.rasterize(
        [(g, 1) for g in geoms],
        out_shape=(meta["height"], meta["width"]),
        transform=transform,
        fill=0,
        dtype="uint8",
    )
    return mask.astype(bool)


def px_to_lonlat(meta: dict, col: float, row: float) -> tuple[float, float]:
    a, b, c, d, e, f = meta["transform"]
    # rasterio maps the pixel corner; use the pixel center.
    lon = c + a * (col + 0.5) + b * (row + 0.5)
    lat = f + d * (col + 0.5) + e * (row + 0.5)
    return float(lon), float(lat)


def run_cfar(meta: dict, force: bool) -> list[dict]:
    out = DEMO / "detections_raw.json"
    if not force and out.exists():
        log("detections already present")
        return json.loads(out.read_text())
    from scipy import ndimage

    log("running CA-CFAR")
    vv = np.load(DEMO / "scene_vv.npz")["vv"]
    land = land_mask(meta)
    land = ndimage.binary_dilation(land, iterations=2)
    ocean = np.isfinite(vv) & (vv > 0) & ~land
    dets = CFARDetector().detect(vv, valid=ocean)
    # Shore distance on the ocean side of the dilated mask.
    shore_px = ndimage.distance_transform_edt(~land)
    m_per_px = meta["resolution_m"]
    rows = []
    for i, det in enumerate(dets, start=1):
        lon, lat = px_to_lonlat(meta, det.col, det.row)
        r = int(round(det.row))
        c = int(round(det.col))
        r = min(max(r, 0), shore_px.shape[0] - 1)
        c = min(max(c, 0), shore_px.shape[1] - 1)
        shore_km = float(shore_px[r, c] * m_per_px / 1000.0)
        rows.append(
            {
                "id": f"D{i:03d}",
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "pixels": det.pixels,
                "peak_db": round(det.peak_db, 2),
                "shore_km": round(shore_km, 2),
            }
        )
    out.write_text(json.dumps(rows))
    log(f"CFAR detections: {len(rows)}")
    return rows


def _parse_ais_time(text: str) -> datetime | None:
    text = text.strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def filter_ais(zip_path: Path, force: bool) -> Path:
    dest = DEMO / "ais_pings.csv.gz"
    if not force and dest.exists() and dest.stat().st_size > 1000:
        log(f"AIS sample already present ({dest.stat().st_size} bytes)")
        return dest
    if not zip_path.exists():
        import httpx

        log(f"downloading AIS zip from {AIS_URL}")
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", AIS_URL, timeout=None, follow_redirects=True) as response:
            response.raise_for_status()
            with zip_path.open("wb") as handle:
                for chunk in response.iter_bytes(1 << 20):
                    handle.write(chunk)
    west, south, east, north = BBOX
    buf = (west - 0.35, south - 0.35, east + 0.35, north + 0.35)
    dense_start = SCENE_TIME - timedelta(minutes=20)
    dense_end = SCENE_TIME + timedelta(minutes=20)
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
            # Expected Danish Maritime Authority columns.
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


def tracks_geojson(tracks: dict[str, list[Fix]]) -> dict:
    west, south, east, north = BBOX
    features = []
    for mmsi, fixes in tracks.items():
        ordered = sorted(fixes, key=lambda f: f.t)
        inside = [f for f in ordered if south <= f.lat <= north and west <= f.lon <= east]
        if len(inside) < 2:
            continue
        # Display at about 3-minute spacing.
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


def match_all(dets: list[dict], tracks: dict[str, list[Fix]], mpas: dict) -> dict:
    scene_tracks = {}
    west, south, east, north = BBOX
    for mmsi, fixes in tracks.items():
        if any(south - 0.2 <= f.lat <= north + 0.2 and west - 0.2 <= f.lon <= east + 0.2 for f in fixes):
            scene_tracks[mmsi] = fixes
    matched = match_detections(dets, scene_tracks, SCENE_TIME, max_km=3.0, max_gap_s=600)
    matched = annotate_mpa(matched, mpas)
    for row in matched:
        if row["matched"]:
            row["confidence"] = None
            row["candidate"] = False
        else:
            row["confidence"] = confidence_score(
                float(row["peak_db"]),
                float(row["shore_km"]),
                int(row["pixels"]),
                row.get("nearest_ais_km"),
            )
            row["candidate"] = True
            row["label"] = "potential dark vessel"
    n_match = sum(1 for r in matched if r["matched"])
    summary = {
        "scene_id": SCENE_ID,
        "scene_time": SCENE_TIME.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bbox": list(BBOX),
        "detections": len(matched),
        "matched": n_match,
        "unmatched": len(matched) - n_match,
        "ais_vessels_with_pings": len(tracks),
        "ais_interpolated_for_match": None,
        "match_radius_km": 3.0,
        "match_max_gap_s": 600,
        "detector": "CA-CFAR",
        "ais_source": AIS_URL,
        "note": "Unmatched means not matched to Danish Maritime Authority public AIS. It is not evidence of wrongdoing.",
    }
    # Count successful interpolations the same way the matcher does.
    from darkwatch.detection.matching import interpolate_track

    n_interp = 0
    for fixes in scene_tracks.values():
        if interpolate_track(fixes, SCENE_TIME, 600) is not None:
            n_interp += 1
    summary["ais_interpolated_for_match"] = n_interp
    return {"summary": summary, "detections": matched}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--ais-zip", default=config.ais_zip() or str(paths.raw_dir() / "aisdk-2026-11-02.zip"))
    parser.add_argument("--skip-catalog", action="store_true")
    args = parser.parse_args()
    DEMO.mkdir(parents=True, exist_ok=True)

    meta = clip_scene(args.force)
    dets = run_cfar(meta, args.force)
    ais_path = filter_ais(Path(args.ais_zip), args.force)
    tracks = load_tracks(ais_path)
    (DEMO / "ais_tracks.geojson").write_text(json.dumps(tracks_geojson(tracks)))
    log(f"display tracks: {sum(1 for _ in json.loads((DEMO / 'ais_tracks.geojson').read_text())['features'])}")

    mpa_path = DEMO / "mpas.geojson"
    if args.force or not mpa_path.exists():
        log("fetching Natura 2000 sites for the Kattegat chip")
        west, south, east, north = BBOX
        raw = fetch_natura2000((west - 0.4, south - 0.4, east + 0.4, north + 0.4))
        simple = simplify_collection(raw)
        mpa_path.write_text(json.dumps(simple))
        log(f"MPA polygons: {len(simple['features'])}")
    else:
        simple = json.loads(mpa_path.read_text())
        log(f"MPA polygons already present: {len(simple.get('features') or [])}")

    result = match_all(dets, tracks, simple)
    (DEMO / "matches.json").write_text(json.dumps(result["detections"]))
    (DEMO / "summary.json").write_text(json.dumps(result["summary"], indent=2))
    log(json.dumps(result["summary"], indent=2))

    if not args.skip_catalog:
        log("refreshing CelesTrak SAR catalog")
        from darkwatch.catalog import get_catalog

        cat = get_catalog(refresh=True)
        families: dict[str, int] = {}
        for sat in cat.satellites:
            families[sat.family] = families.get(sat.family, 0) + 1
        log(f"catalog {len(cat.satellites)} sats at {cat.fetched_at}: {families}")
        log(f"skipped {len(cat.skipped)}")


if __name__ == "__main__":
    main()
