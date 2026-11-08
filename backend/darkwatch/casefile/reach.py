"""Reachable-area disks for a dark candidate.

Radius is hours × knots × 1.852 km. Disks are geodesic buffers in a local
azimuthal-equidistant frame. Land is clipped only when a Natural Earth shapefile
is already on disk.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pyproj import CRS, Transformer
from shapely.geometry import Point, mapping, shape
from shapely.ops import transform as shp_transform

from darkwatch import paths
from darkwatch.orbit.geometry import haversine_km

KN_KM = 1.852
SPEED_KN = {"slow": 6.0, "typical": 12.0, "fast": 20.0}
QUAD_SEGS = 32


def reach_radius_km(hours: float, speed_kn: float) -> float:
    return max(0.0, float(hours) * float(speed_kn) * KN_KM)


def aeqd_transformers(lat: float, lon: float):
    aeqd = CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat} +lon_0={lon} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
    )
    wgs = CRS.from_epsg(4326)
    fwd_t = Transformer.from_crs(wgs, aeqd, always_xy=True)
    inv_t = Transformer.from_crs(aeqd, wgs, always_xy=True)

    def fwd(x, y, z=None):
        return fwd_t.transform(x, y)

    def inv(x, y, z=None):
        return inv_t.transform(x, y)

    return fwd, inv


def geodesic_disk(lat: float, lon: float, radius_km: float, quad_segs: int = QUAD_SEGS):
    if radius_km <= 0:
        return Point(lon, lat)
    fwd, inv = aeqd_transformers(lat, lon)
    center = shp_transform(fwd, Point(lon, lat))
    disk = center.buffer(radius_km * 1000.0, quad_segs=quad_segs)
    return shp_transform(inv, disk)


def projected_area_m2(geom, lat: float, lon: float) -> float:
    fwd, _inv = aeqd_transformers(lat, lon)
    return float(shp_transform(fwd, geom).area)


def coverage_fraction(swath, disk, lat: float, lon: float) -> float:
    """area(swath ∩ disk) / area(disk) in the local AEQD frame."""
    if disk.is_empty:
        return 0.0
    fwd, _inv = aeqd_transformers(lat, lon)
    disk_p = shp_transform(fwd, disk)
    if disk_p.area <= 0:
        return 0.0
    swath_p = shp_transform(fwd, swath)
    inter = swath_p.intersection(disk_p)
    frac = float(inter.area / disk_p.area)
    if frac > 1.0:
        return 1.0
    if frac < 0.0:
        return 0.0
    return frac


def as_geojson(geom) -> dict:
    return mapping(geom)


def from_geojson(obj) -> object:
    if obj is None:
        raise ValueError("missing geometry")
    if obj.get("type") == "Feature":
        obj = obj.get("geometry")
    if not obj:
        raise ValueError("missing geometry")
    return shape(obj)


def polygon_radius_km(geom, lat: float, lon: float) -> float:
    coords = []
    if geom.geom_type == "Polygon":
        coords = list(geom.exterior.coords)
    elif geom.geom_type == "MultiPolygon":
        for part in geom.geoms:
            coords.extend(part.exterior.coords)
    else:
        coords = list(geom.convex_hull.exterior.coords)
    if not coords:
        return 0.0
    return max(haversine_km(lat, lon, y, x) for x, y in coords)


def _land_paths() -> list[Path]:
    return [
        Path("/tmp/darkwatch-ne/ne_10m_land.shp"),
        paths.raw_dir() / "ne_10m_land" / "ne_10m_land.shp",
        paths.raw_dir() / "ne_10m_land.shp",
    ]


@lru_cache(maxsize=1)
def _land_reader_path() -> str | None:
    for path in _land_paths():
        if path.is_file():
            return str(path)
    return None


def land_available() -> bool:
    return _land_reader_path() is not None


@lru_cache(maxsize=8)
def _land_in_window(bounds: tuple[float, float, float, float]):
    path = _land_reader_path()
    if path is None:
        return None
    try:
        import shapefile
        from shapely.geometry import box, shape as shp_shape
        from shapely.ops import unary_union
    except ImportError:
        return None
    window = box(*bounds)
    try:
        reader = shapefile.Reader(path)
        geoms = []
        for sr in reader.shapes():
            geo = sr.__geo_interface__
            if not geo:
                continue
            poly = shp_shape(geo)
            if poly.intersects(window):
                geoms.append(poly.intersection(window))
        if not geoms:
            return window.difference(window)  # empty
        return unary_union(geoms)
    except Exception:
        return None


def clip_to_sea(geom):
    if geom.is_empty or not land_available():
        return geom, False
    minx, miny, maxx, maxy = geom.bounds
    pad = 2.0
    key = (round(minx - pad, 1), round(miny - pad, 1), round(maxx + pad, 1), round(maxy + pad, 1))
    local = _land_in_window(key)
    if local is None:
        return geom, False
    if local.is_empty:
        return geom, True
    sea = geom.difference(local)
    return (sea if not sea.is_empty else geom), True
