import json
from datetime import timedelta
from pathlib import Path

from nimbus.orbit import epoch_of, haversine_km, propagate_one, satrec_from_omm, tle_lines

FIXTURE = Path(__file__).parent / "fixtures" / "s1d_gp.json"


def _omm():
    data = json.loads(FIXTURE.read_text())
    return data[0]


def test_sentinel_1d_altitude_near_epoch():
    omm = _omm()
    sat = satrec_from_omm(omm)
    epoch = epoch_of(sat)
    pos = propagate_one(sat, epoch + timedelta(minutes=10))
    assert pos is not None
    assert 660 < pos["alt_km"] < 740
    assert -90 <= pos["lat"] <= 90


def test_ground_track_moves():
    sat = satrec_from_omm(_omm())
    epoch = epoch_of(sat)
    a = propagate_one(sat, epoch + timedelta(minutes=5))
    b = propagate_one(sat, epoch + timedelta(minutes=15))
    moved = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
    # LEO ground speed is roughly 400 km per minute? No: 7 km/s * 600 s = 4200 km.
    assert 3000 < moved < 5500


def test_tle_lines_parse_shape():
    omm = _omm()
    sat = satrec_from_omm(omm)
    line1, line2 = tle_lines(sat, int(omm["NORAD_CAT_ID"]))
    assert line1.startswith("1 ")
    assert line2.startswith("2 ")
    assert len(line1) == 69
    assert len(line2) == 69
    assert line1[-1].isdigit() and line2[-1].isdigit()
