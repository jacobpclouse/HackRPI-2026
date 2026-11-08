#!/usr/bin/env python3
"""Download Natural Earth 10m ports, land, and countries for the Kattegat report.

Clips to [10.0, 55.3, 13.2, 58.2], simplifies linework to about 50 m, and writes
committed GeoJSON under data/reference/. Raw zips stay in data/raw/ (gitignored).

Verified 8 Nov 2026 against naciscdn.org (HTTP 200, application/zip):
  https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip
  https://naciscdn.org/naturalearth/10m/cultural/ne_10m_ports.zip
  https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip
"""

from __future__ import annotations

import json
import logging
import sys
import zipfile
from pathlib import Path

import httpx
from pyproj import CRS, Transformer
from shapely.geometry import box, mapping, shape
from shapely.ops import transform as shp_transform
from shapely.ops import unary_union

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from darkwatch import paths  # noqa: E402

log = logging.getLogger("darkwatch.reference")

# west, south, east, north — Kattegat window from CURSOR_PROMPT_REPORT.md
BBOX = (10.0, 55.3, 13.2, 58.2)
SIMPLIFY_M = 50.0
TIMEOUT_S = 120

LAYERS = (
    {
        "id": "land",
        "url": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip",
        "shp_name": "ne_10m_land.shp",
        "kind": "polygon",
        "out": "land.geojson",
        "props": (),
    },
    {
        "id": "ports",
        "url": "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_ports.zip",
        "shp_name": "ne_10m_ports.shp",
        "kind": "point",
        "out": "ports.geojson",
        "props": ("name", "natlscale", "scalerank", "website"),
    },
    {
        "id": "countries",
        "url": "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip",
        "shp_name": "ne_10m_admin_0_countries.shp",
        "kind": "polygon",
        "out": "countries.geojson",
        "props": ("ADMIN", "NAME", "ISO_A3", "ISO_A2"),
    },
)

ATTRIBUTION = """# Attribution

Natural Earth 10m land, ports, and admin-0 countries.

https://www.naturalearthdata.com

Public domain (Natural Earth terms). Downloaded from the Natural Earth CDN
(https://naciscdn.org). Clipped to the Kattegat window
`[10.0, 55.3, 13.2, 58.2]` (west, south, east, north) and simplified to about
50 m. Jurisdiction on the report is nearest-coastline plus 12 nm, not official
maritime boundaries.
"""


def _aeqd(lat: float, lon: float):
    crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat} +lon_0={lon} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
    )
    wgs = CRS.from_epsg(4326)
    fwd_t = Transformer.from_crs(wgs, crs, always_xy=True)
    inv_t = Transformer.from_crs(crs, wgs, always_xy=True)

    def fwd(x, y, z=None):
        return fwd_t.transform(x, y)

    def inv(x, y, z=None):
        return inv_t.transform(x, y)

    return fwd, inv


def _simplify(geom, lat: float, lon: float):
    if geom.is_empty:
        return geom
    fwd, inv = _aeqd(lat, lon)
    projected = shp_transform(fwd, geom)
    simple = projected.simplify(SIMPLIFY_M, preserve_topology=True)
    return shp_transform(inv, simple)


def _clean_geom(geom):
    geom = geom if geom.is_valid else geom.buffer(0)
    if hasattr(geom, "force_2d"):
        geom = geom.force_2d()
    return geom


def _download(url: str, dest_zip: Path) -> Path | None:
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    try:
        log.info("downloading %s", url)
        response = httpx.get(url, timeout=TIMEOUT_S, follow_redirects=True)
        response.raise_for_status()
    except Exception as exc:
        log.error("download failed for %s: %s", url, exc)
        return None
    dest_zip.write_bytes(response.content)
    return dest_zip


def _extract_shp(zpath: Path, shp_name: str, dest_dir: Path) -> Path | None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zpath) as archive:
            archive.extractall(dest_dir)
    except Exception as exc:
        log.error("extract failed for %s: %s", zpath, exc)
        return None
    found = list(dest_dir.rglob(shp_name))
    if not found:
        log.error("shapefile %s missing after extract of %s", shp_name, zpath.name)
        return None
    return found[0]


def _read_features(shp: Path) -> list[tuple[object, dict]]:
    import shapefile

    reader = shapefile.Reader(str(shp))
    fields = [item[0] for item in reader.fields[1:]]
    out = []
    for sr in reader.shapeRecords():
        geo = sr.shape.__geo_interface__
        if not geo:
            continue
        props = {key: sr.record[i] for i, key in enumerate(fields)}
        out.append((shape(geo), props))
    return out


def _pick_props(props: dict, keys: tuple[str, ...]) -> dict:
    if not keys:
        return {}
    out = {}
    lookup = {str(k).lower(): k for k in props}
    for key in keys:
        src = lookup.get(key.lower())
        if src is None:
            continue
        val = props[src]
        if val in (None, ""):
            continue
        out[key.lower() if key != "ISO_A3" and key != "ISO_A2" else key] = val
    return out


def _attach_port_country(features: list[dict], country_fc: dict | None) -> None:
    if not country_fc:
        return
    geoms = []
    for feat in country_fc.get("features") or []:
        try:
            geoms.append((shape(feat["geometry"]), feat.get("properties") or {}))
        except Exception:
            continue
    for feat in features:
        pt = shape(feat["geometry"])
        name = None
        for geom, props in geoms:
            if geom.covers(pt) or geom.contains(pt):
                name = props.get("name") or props.get("admin")
                break
        if name is None:
            best = None
            best_d = None
            for geom, props in geoms:
                d = pt.distance(geom)
                if best_d is None or d < best_d:
                    best_d = d
                    best = props.get("name") or props.get("admin")
            name = best
        if name:
            feat["properties"]["country"] = name


def _process_layer(layer: dict, window, lat0: float, lon0: float) -> dict | None:
    raw_dir = paths.raw_dir() / "naturalearth" / layer["id"]
    zpath = raw_dir / Path(layer["url"]).name
    if not zpath.is_file():
        if _download(layer["url"], zpath) is None:
            return None
    shp = _extract_shp(zpath, layer["shp_name"], raw_dir)
    if shp is None:
        return None
    try:
        records = _read_features(shp)
    except Exception as exc:
        log.error("read failed for %s: %s", layer["id"], exc)
        return None
    features = []
    pieces = []
    for geom, props in records:
        geom = _clean_geom(geom)
        if geom.is_empty or not geom.intersects(window):
            continue
        clipped = _clean_geom(geom.intersection(window))
        if clipped.is_empty:
            continue
        if layer["kind"] == "polygon":
            clipped = _simplify(clipped, lat0, lon0)
            if clipped.is_empty:
                continue
            pieces.append(clipped)
        props_out = _pick_props(props, layer["props"])
        if layer["id"] == "countries":
            props_out["name"] = props_out.get("name") or props_out.get("admin")
            props_out["admin"] = props_out.get("admin") or props_out.get("name")
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(clipped),
                "properties": props_out,
            }
        )
    if layer["id"] == "land" and pieces:
        merged = _simplify(_clean_geom(unary_union(pieces)), lat0, lon0)
        features = [
            {
                "type": "Feature",
                "geometry": mapping(merged),
                "properties": {"source": "Natural Earth 10m land"},
            }
        ]
    return {
        "type": "FeatureCollection",
        "name": layer["id"],
        "features": features,
        "properties": {
            "source": "Natural Earth 10m (public domain)",
            "url": layer["url"],
            "bbox": list(BBOX),
            "simplified_m": SIMPLIFY_M if layer["kind"] == "polygon" else None,
        },
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    west, south, east, north = BBOX
    window = box(west, south, east, north)
    lat0 = (south + north) / 2.0
    lon0 = (west + east) / 2.0
    out_dir = paths.reference_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    failed = []
    for layer in LAYERS:
        fc = _process_layer(layer, window, lat0, lon0)
        if fc is None:
            failed.append(layer["id"])
            continue
        dest = out_dir / layer["out"]
        dest.write_text(json.dumps(fc, ensure_ascii=False))
        size_kb = dest.stat().st_size / 1024.0
        log.info("wrote %s (%d features, %.0f KB)", dest, len(fc["features"]), size_kb)
        if size_kb > 2048:
            log.warning("%s is over 2 MB; consider a coarser simplify", dest.name)
        written[layer["id"]] = fc
    if "ports" in written:
        _attach_port_country(written["ports"]["features"], written.get("countries"))
        (out_dir / "ports.geojson").write_text(json.dumps(written["ports"], ensure_ascii=False))
    (out_dir / "ATTRIBUTION.md").write_text(ATTRIBUTION)
    if failed:
        log.error("failed layers: %s (other layers were still written)", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
