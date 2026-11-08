import math

from nimbus.orbit import along_cross_km, bearing_deg, destination, ground_range_km, haversine_km


def test_east_of_northbound_track_is_positive_cross():
    along, cross = along_cross_km(56.0, 11.0, 0.0, 56.0, 11.2)
    assert abs(along) < 2
    assert cross > 10


def test_west_of_northbound_track_is_negative_cross():
    _along, cross = along_cross_km(56.0, 11.0, 0.0, 56.0, 10.8)
    assert cross < -10


def test_destination_roundtrip():
    lat, lon = destination(56.9, 11.8, 90, 25)
    back_lat, back_lon = destination(lat, lon, 270, 25)
    assert abs(back_lat - 56.9) < 0.02
    assert abs(back_lon - 11.8) < 0.02
    assert 20 < haversine_km(56.9, 11.8, lat, lon) < 30


def test_bearing_east():
    assert abs(bearing_deg(0, 0, 0, 1) - 90) < 0.1


def test_sentinel1_iw_ground_range_is_a_wide_swath():
    near = ground_range_km(693, 29.1)
    far = ground_range_km(693, 46.0)
    width = far - near
    assert 180 < width < 320
    assert far > near > 100
    assert math.isfinite(width)
