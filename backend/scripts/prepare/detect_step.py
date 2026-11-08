"""CA-CFAR, AIS matching, and the committed summary."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from nimbus.detection import CFARDetector, Fix, confidence_score, match_detections
from nimbus.geo import annotate_mpa
from prepare import Target, log


def ensure_land_shp(ne_url: str) -> Path:
    shp = Path("/tmp/nimbus-ne/ne_10m_land.shp")
    if shp.exists():
        return shp
    import io
    import zipfile as zf

    import httpx

    log("downloading Natural Earth 10m land")
    response = httpx.get(ne_url, timeout=120, follow_redirects=True)
    response.raise_for_status()
    dest = Path("/tmp/nimbus-ne")
    dest.mkdir(parents=True, exist_ok=True)
    with zf.ZipFile(io.BytesIO(response.content)) as archive:
        archive.extractall(dest)
    return shp


def land_mask(target: Target, meta: dict) -> np.ndarray:
    import shapefile
    from rasterio import features
    from rasterio.transform import Affine
    from shapely.geometry import box, shape

    west, south, east, north = meta["bbox"]
    transform = Affine(*meta["transform"])
    region = box(west, south, east, north)
    reader = shapefile.Reader(str(ensure_land_shp(target.ne_url)))
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
    lon = c + a * (col + 0.5) + b * (row + 0.5)
    lat = f + d * (col + 0.5) + e * (row + 0.5)
    return float(lon), float(lat)


def run_cfar(target: Target, meta: dict, force: bool = False) -> list[dict]:
    out = target.out_dir / "detections_raw.json"
    if not force and out.exists():
        log("detections already present")
        return json.loads(out.read_text())
    from scipy import ndimage

    log("running CA-CFAR")
    vv = np.load(target.out_dir / "scene_vv.npz")["vv"]
    land = land_mask(target, meta)
    land = ndimage.binary_dilation(land, iterations=2)
    ocean = np.isfinite(vv) & (vv > 0) & ~land
    dets = CFARDetector().detect(vv, valid=ocean)
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


def match_all(target: Target, dets: list[dict], tracks: dict[str, list[Fix]], mpas: dict) -> dict:
    scene_tracks = {}
    west, south, east, north = target.bbox
    for mmsi, fixes in tracks.items():
        if any(south - 0.2 <= f.lat <= north + 0.2 and west - 0.2 <= f.lon <= east + 0.2 for f in fixes):
            scene_tracks[mmsi] = fixes
    matched = match_detections(dets, scene_tracks, target.scene_time, max_km=3.0, max_gap_s=600)
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
        "scene_id": target.scene_id,
        "scene_time": target.scene_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bbox": list(target.bbox),
        "detections": len(matched),
        "matched": n_match,
        "unmatched": len(matched) - n_match,
        "ais_vessels_with_pings": len(tracks),
        "ais_interpolated_for_match": None,
        "match_radius_km": 3.0,
        "match_max_gap_s": 600,
        "detector": "CA-CFAR",
        "ais_source": target.ais_url,
        "note": "Unmatched means not matched to Danish Maritime Authority public AIS. It is not evidence of wrongdoing.",
    }
    from nimbus.detection.matching import interpolate_track

    n_interp = 0
    for fixes in scene_tracks.values():
        if interpolate_track(fixes, target.scene_time, 600) is not None:
            n_interp += 1
    summary["ais_interpolated_for_match"] = n_interp
    return {"summary": summary, "detections": matched}


def run(target: Target, *, force: bool = False, tracks=None, mpas=None, meta=None) -> dict:
    if meta is None:
        meta = json.loads((target.out_dir / "scene_meta.json").read_text())
    dets = run_cfar(target, meta, force)
    if tracks is None:
        from prepare.ais_step import load_tracks

        tracks = load_tracks(target.out_dir / "ais_pings.csv.gz")
    if mpas is None:
        mpas = json.loads((target.out_dir / "mpas.geojson").read_text())
    result = match_all(target, dets, tracks, mpas)
    (target.out_dir / "matches.json").write_text(json.dumps(result["detections"]))
    (target.out_dir / "summary.json").write_text(json.dumps(result["summary"], indent=2))
    log(json.dumps(result["summary"], indent=2))
    return result
