"""Planetary Computer STAC read and the Kattegat Sentinel-1 RTC chip."""

from __future__ import annotations

import json
import math

import numpy as np

from prepare import Target, log


def sign_href(href: str) -> str:
    import httpx

    response = httpx.get(
        "https://planetarycomputer.microsoft.com/api/sas/v1/sign",
        params={"href": href},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["href"]


def fetch_stac_item(scene_id: str) -> dict:
    import httpx

    response = httpx.post(
        "https://planetarycomputer.microsoft.com/api/stac/v1/search",
        json={"collections": ["sentinel-1-rtc"], "ids": [scene_id], "limit": 1},
        timeout=60,
    )
    response.raise_for_status()
    features = response.json().get("features") or []
    if not features:
        raise SystemExit(f"STAC item not found: {scene_id}")
    return features[0]


def clip_scene(target: Target, force: bool = False) -> dict:
    meta_path = target.out_dir / "scene_meta.json"
    npz_path = target.out_dir / "scene_vv.npz"
    png_path = target.out_dir / "scene_preview.png"
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
    item = fetch_stac_item(target.scene_id)
    props = item["properties"]
    href = item["assets"]["vv"]["href"]
    signed = sign_href(href)
    west, south, east, north = target.bbox
    with rasterio.open("/vsicurl/" + signed) as src:
        log(f"opened {src.width}x{src.height} {src.crs} dtype={src.dtypes}")
        sb = transform_bounds("EPSG:4326", src.crs, west, south, east, north, densify_pts=21)
        window = window_from_bounds(*sb, transform=src.transform).intersection(
            Window(0, 0, src.width, src.height)
        )
        if window.width < 10 or window.height < 10:
            raise SystemExit(f"bbox missed the scene footprint: {window}")
        scale = max(1.0, target.res_m / 10.0)
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
    dst_w = max(32, int((east - west) * 111_320 * math.cos(math.radians(mean_lat)) / target.res_m))
    dst_h = max(32, int((north - south) * 111_320 / target.res_m))
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

    db = 10.0 * np.log10(np.clip(np.where(valid, dst, 1e-5), 1e-5, None))
    sample = db[valid]
    lo, hi = np.percentile(sample, [8, 99.2]) if sample.size else (-25, 0)
    scaled = np.clip((db - lo) / max(1e-3, hi - lo), 0, 1)
    gray = (np.where(valid, scaled, 0) * 255).astype(np.uint8)
    alpha = np.where(valid, 255, 0).astype(np.uint8)
    target.out_dir.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.dstack([gray, gray, gray, alpha]), mode="RGBA").save(png_path)

    np.savez_compressed(npz_path, vv=np.nan_to_num(dst, nan=0).astype(np.float16))
    meta = {
        "scene_id": target.scene_id,
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
        "resolution_m": target.res_m,
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


def run(target: Target, *, force: bool = False) -> dict:
    return clip_scene(target, force)
