"""Reach radius, geodesic disk area, and swath coverage fractions."""

import math

from shapely.geometry import box
from shapely.ops import transform as shp_transform

from darkwatch.casefile.reach import (
    aeqd_transformers,
    coverage_fraction,
    geodesic_disk,
    projected_area_m2,
    reach_radius_km,
)


def test_reach_radius_is_hours_times_knots_times_1852():
    assert reach_radius_km(1, 10) == 18.52
    assert reach_radius_km(2, 12) == 44.448
    assert reach_radius_km(0, 20) == 0


def test_disk_area_within_one_percent_at_kattegat():
    lat, lon = 56.9, 11.8
    radius_km = 50.0
    disk = geodesic_disk(lat, lon, radius_km)
    area = projected_area_m2(disk, lat, lon)
    expected = math.pi * (radius_km * 1000.0) ** 2
    assert abs(area - expected) / expected < 0.01


def test_coverage_fraction_contains_disjoint_and_half_plane():
    lat, lon = 56.9, 11.8
    disk = geodesic_disk(lat, lon, 40)
    contains = geodesic_disk(lat, lon, 120)
    assert coverage_fraction(contains, disk, lat, lon) == 1.0

    disjoint = geodesic_disk(lat + 5.0, lon, 40)
    assert coverage_fraction(disjoint, disk, lat, lon) == 0.0

    fwd, inv = aeqd_transformers(lat, lon)
    disk_p = shp_transform(fwd, disk)
    half = box(0, -1e7, 1e7, 1e7)
    swath = shp_transform(inv, disk_p.intersection(half))
    assert abs(coverage_fraction(swath, disk, lat, lon) - 0.5) < 0.05
