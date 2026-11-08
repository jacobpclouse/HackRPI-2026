"""GeoTIFF ingest: spacing, 8-bit sea-brightness match, acquisition time."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from darkwatch.imagery import preprocess

FILENAME_TIME = re.compile(r"_(\d{8}T\d{6})_")
TARGET_M = 10.0
SPACING_TOL = 0.20


@dataclass
class GeoImage:
    array: np.ndarray  # uint8
    spacing_m: float
    spacing_note: str
    bbox: list[float] | None  # west, south, east, north
    transform: object | None
    crs: str | None
    width: int
    height: int
    resampled: bool
    value_type: str
    acquisition: dict | None
    valid: np.ndarray | None = None


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_acquisition(tags: dict, filename: str, user_time: str | None) -> dict | None:
    raw = tags.get("DARKWATCH_ACQUISITION_TIME")
    if raw:
        return {"time": _normalize_time(raw), "source": "geotiff_tag"}
    raw = tags.get("TIFFTAG_DATETIME")
    if raw:
        return {"time": _normalize_time(raw), "source": "tiff_datetime"}
    match = FILENAME_TIME.search(filename or "")
    if match:
        stamp = match.group(1)
        when = datetime.strptime(stamp, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        return {"time": _iso(when), "source": "filename"}
    if user_time:
        return {"time": _normalize_time(user_time), "source": "user"}
    return None


def _normalize_time(value: str) -> str:
    text = str(value).strip().replace(" ", "T")
    if text.endswith("+00:00"):
        text = text[:-6] + "Z"
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y:%m:%dT%H:%M:%S"):
        try:
            when = datetime.strptime(str(value).strip(), fmt).replace(tzinfo=timezone.utc)
            return _iso(when)
        except ValueError:
            pass
    if not text.endswith("Z") and "T" in text:
        text += "Z"
    datetime.fromisoformat(text.replace("Z", "+00:00"))
    return text if text.endswith("Z") else text + "Z"


def _spacing_m(src) -> float:
    res_x, res_y = abs(src.res[0]), abs(src.res[1])
    crs = src.crs
    if crs is None:
        return float((res_x + res_y) / 2)
    if getattr(crs, "is_projected", False):
        return float((res_x + res_y) / 2)
    west, south, east, north = src.bounds
    lat = (south + north) / 2
    mx = res_x * 111_320 * max(0.2, math.cos(math.radians(lat)))
    my = res_y * 111_320
    return float((mx + my) / 2)


def _detect_type(arr: np.ndarray, valid: np.ndarray) -> str:
    if arr.dtype == np.uint8:
        return "uint8"
    sample = arr[valid]
    if sample.size == 0:
        return "linear"
    if sample.dtype.kind == "f" and float(np.nanmedian(sample)) < 0:
        return "db"
    return "linear"


def _to_db(arr: np.ndarray, valid: np.ndarray, kind: str) -> np.ndarray:
    if kind == "db":
        return arr
    if kind == "uint8":
        return arr.astype(np.float32)
    work = np.where(valid, arr, np.nan).astype(np.float32)
    return np.where(np.isfinite(work) & (work > 0), 10.0 * np.log10(np.clip(work, 1e-6, None)), np.nan)


def _land_mask(src) -> np.ndarray | None:
    """Optional Natural Earth land mask. Returns None when the shapefile is not on disk."""
    try:
        from darkwatch.geo.regions import land_mask_for  # type: ignore
    except ImportError:
        return None
    try:
        return land_mask_for(src)
    except Exception:
        return None


def _sea_percentiles(values: np.ndarray) -> tuple[float, float]:
    p50, p99 = np.percentile(values, [50, 99])
    if p99 <= p50:
        p99 = p50 + 1.0
    return float(p50), float(p99)


def load(path: Path, filename: str = "", user_time: str | None = None) -> GeoImage:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import transform_bounds

    with rasterio.open(path) as src:
        arr = src.read(1)
        nodata = src.nodata
        tags = {**src.tags(), **src.tags(1)}
        spacing = _spacing_m(src)
        resampled = False
        transform = src.transform
        crs = src.crs
        if abs(spacing - TARGET_M) / TARGET_M > SPACING_TOL:
            scale = spacing / TARGET_M
            out_h = max(32, int(round(src.height * scale)))
            out_w = max(32, int(round(src.width * scale)))
            arr = src.read(1, out_shape=(out_h, out_w), resampling=Resampling.bilinear)
            from rasterio.transform import Affine

            transform = Affine(
                src.transform.a * src.width / out_w,
                src.transform.b,
                src.transform.c,
                src.transform.d,
                src.transform.e * src.height / out_h,
                src.transform.f,
            )
            spacing = TARGET_M
            resampled = True
            height, width = arr.shape
        else:
            height, width = arr.shape
        valid = np.isfinite(arr)
        if nodata is not None:
            valid &= arr != nodata
        if arr.dtype != np.uint8:
            valid &= arr > -1e8
        land = _land_mask(src)
        sea = valid if land is None else valid & ~land
        kind = _detect_type(arr, valid)
        if kind == "uint8":
            img8 = arr.astype(np.uint8)
            img8 = np.where(valid, img8, 0)
        else:
            db = _to_db(arr.astype(np.float32), valid, kind)
            sample = db[sea & np.isfinite(db)]
            if sample.size == 0:
                sample = db[valid & np.isfinite(db)]
            src50, src99 = _sea_percentiles(sample) if sample.size else (0.0, 1.0)
            ref50, ref99 = preprocess.ref_p50(), preprocess.ref_p99()
            mapped = ref50 + (db - src50) * (ref99 - ref50) / max(1e-6, src99 - src50)
            img8 = np.clip(np.nan_to_num(mapped, nan=0.0), 0, 255).astype(np.uint8)
            img8 = np.where(valid, img8, 0)
        bbox = None
        crs_s = None
        if crs is not None:
            crs_s = str(crs)
            try:
                w, s, e, n = transform_bounds(crs, "EPSG:4326", *src.bounds, densify_pts=21)
                bbox = [float(w), float(s), float(e), float(n)]
            except Exception:
                bbox = [float(src.bounds.left), float(src.bounds.bottom), float(src.bounds.right), float(src.bounds.top)]
        acq = parse_acquisition(tags, filename or path.name, user_time)
        return GeoImage(
            array=img8,
            spacing_m=float(spacing),
            spacing_note="resampled to 10 m" if resampled else "native",
            bbox=bbox,
            transform=transform,
            crs=crs_s,
            width=int(width),
            height=int(height),
            resampled=resampled,
            value_type=kind,
            acquisition=acq,
            valid=valid,
        )


def pixel_to_lonlat(geo: GeoImage, row: float, col: float) -> tuple[float, float] | None:
    if geo.transform is None or not geo.crs:
        return None
    from rasterio.transform import xy
    from rasterio.warp import transform as warp_transform

    x, y = xy(geo.transform, row, col)
    if str(geo.crs) in ("EPSG:4326", "OGC:CRS84"):
        return float(x), float(y)
    try:
        lons, lats = warp_transform(geo.crs, "EPSG:4326", [x], [y])
        return float(lons[0]), float(lats[0])
    except Exception:
        return None
