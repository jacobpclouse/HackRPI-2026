"""Natural Earth reference loaders, jurisdiction, and nearest ports."""

from shapely.geometry import Point

from nimbus.casefile.candidates import match_row
from nimbus.geo import reference as ref


def test_jurisdiction_for_dark_candidates():
    for det_id in ("D002", "D016"):
        row = match_row(det_id)
        jur = ref.jurisdiction(row["lat"], row["lon"])
        assert jur is not None
        assert jur["nearest_coast_country"] in {"Denmark", "Sweden"}
        assert jur["likely_territorial_sea"] == (jur["distance_to_coast_km"] <= 22.2)
        assert "Official maritime boundaries were not computed" in jur["method"]


def test_nearest_ports_sorted_with_bearings():
    row = match_row("D016")
    ports = ref.nearest_ports(row["lat"], row["lon"], n=3)
    assert ports is not None
    assert len(ports) == 3
    dists = [p["distance_km"] for p in ports]
    assert dists == sorted(dists)
    for port in ports:
        assert 0 <= port["bearing_deg"] < 360
        assert port["bearing_compass"]
        assert port["name"]


def test_missing_reference_files_return_none(tmp_path, monkeypatch):
    monkeypatch.setattr(ref, "_path", lambda name: tmp_path / name)
    ref.clear_cache()
    assert ref.load_ports() is None
    assert ref.load_land() is None
    assert ref.load_countries() is None
    assert ref.jurisdiction(56.9, 11.9) is None
    assert ref.nearest_ports(56.9, 11.9) is None
    sea, clipped = ref.clip_to_sea(Point(11.9, 56.9).buffer(0.01))
    assert clipped is False
    ref.clear_cache()
