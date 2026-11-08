import json
from datetime import timedelta
from pathlib import Path

from nimbus.catalog import SatRecord, classify
from nimbus.orbit import (
    coverage_gaps,
    destination,
    epoch_of,
    find_passes,
    in_swath,
    longest_gap,
    propagate_many,
    satrec_from_omm,
    spec_of,
    swath_polygon,
)

FIXTURE = Path(__file__).parent / "fixtures" / "s1d_gp.json"


def _record() -> SatRecord:
    omm = json.loads(FIXTURE.read_text())[0]
    spec = classify("SENTINEL-1D")
    assert spec is not None
    sat = satrec_from_omm(omm)
    return SatRecord(
        norad=int(omm["NORAD_CAT_ID"]),
        name="SENTINEL-1D",
        family=spec.family,
        coverage=spec.coverage,
        look=spec.look,
        inc_near=spec.inc_near,
        inc_far=spec.inc_far,
        access_inc=spec.access_inc,
        nominal_width_km=spec.nominal_width_km,
        color=spec.color,
        note=spec.note,
        epoch=epoch_of(sat).strftime("%Y-%m-%dT%H:%M:%SZ"),
        tle1="",
        tle2="",
        omm=omm,
    )


def test_point_placed_in_the_swath_is_a_pass():
    rec = _record()
    sat = satrec_from_omm(rec.omm)
    epoch = epoch_of(sat)
    when = epoch + timedelta(minutes=20)
    pos = propagate_many(sat, [when, when + timedelta(seconds=20)])
    from nimbus.orbit import bearing_deg

    heading = bearing_deg(pos["lat"][0], pos["lon"][0], pos["lat"][1], pos["lon"][1])
    # Mid-swath, right of track.
    from nimbus.orbit import ground_range_km

    mid = 0.5 * (
        ground_range_km(float(pos["alt_km"][0]), rec.inc_near)
        + ground_range_km(float(pos["alt_km"][0]), rec.inc_far)
    )
    lat, lon = destination(float(pos["lat"][0]), float(pos["lon"][0]), (heading + 90) % 360, mid)
    passes = find_passes(rec, lat, lon, when - timedelta(minutes=8), when + timedelta(minutes=8), step_s=20)
    assert passes, "expected the constructed point to fall inside the Sentinel-1 swath"
    assert passes[0].coverage == "systematic"
    assert abs((passes[0].center - when).total_seconds()) < 180


def test_left_of_track_is_not_a_sentinel_pass():
    rec = _record()
    sat = satrec_from_omm(rec.omm)
    epoch = epoch_of(sat)
    when = epoch + timedelta(minutes=20)
    pos = propagate_many(sat, [when, when + timedelta(seconds=20)])
    from nimbus.orbit import bearing_deg, ground_range_km

    heading = bearing_deg(pos["lat"][0], pos["lon"][0], pos["lat"][1], pos["lon"][1])
    mid = 0.5 * (
        ground_range_km(float(pos["alt_km"][0]), rec.inc_near)
        + ground_range_km(float(pos["alt_km"][0]), rec.inc_far)
    )
    lat, lon = destination(float(pos["lat"][0]), float(pos["lon"][0]), (heading - 90) % 360, mid)
    passes = find_passes(rec, lat, lon, when - timedelta(minutes=6), when + timedelta(minutes=6), step_s=20)
    assert passes == []


def test_in_swath_respects_look_side():
    rec = _record()
    spec = spec_of(rec)
    assert in_swath(400, 693, spec)
    assert not in_swath(-400, 693, spec)


def test_swath_polygon_sits_on_the_right():
    rec = _record()
    sat = satrec_from_omm(rec.omm)
    when = epoch_of(sat) + timedelta(minutes=12)
    feature = swath_polygon(rec, when, half_s=40, step_s=10)
    ring = feature["geometry"]["coordinates"][0]
    assert len(ring) > 4
    assert feature["properties"]["coverage"] == "systematic"


def test_gaps_are_the_holes_between_windows():
    rec = _record()
    sat = satrec_from_omm(rec.omm)
    t0 = epoch_of(sat)
    # Two synthetic passes inside a 10 hour window.
    from nimbus.orbit import Pass

    p1 = Pass(1, "A", "Sentinel-1", "systematic", t0 + timedelta(hours=1), t0 + timedelta(hours=1, minutes=1), t0 + timedelta(hours=1), 10, 700, "#fff")
    p2 = Pass(1, "A", "Sentinel-1", "systematic", t0 + timedelta(hours=4), t0 + timedelta(hours=4, minutes=1), t0 + timedelta(hours=4), 10, 700, "#fff")
    t1 = t0 + timedelta(hours=10)
    gaps = coverage_gaps([p2, p1], t0, t1)
    durations = [round(g.duration_s) for g in gaps]
    assert durations[0] == 3600
    assert durations[1] == 3 * 3600 - 60
    assert durations[2] == 6 * 3600 - 60
    assert longest_gap(gaps).duration_s == max(g.duration_s for g in gaps)
    # Empty schedule is one gap spanning the whole window — still computed.
    only = coverage_gaps([], t0, t1)
    assert len(only) == 1
    assert only[0].duration_s == 10 * 3600
