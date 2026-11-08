"""Deterministic case-file facts."""

import json
import re

from shapely.geometry import Point
from shapely.geometry import box as shp_box

from nimbus.casefile.candidates import match_row
from nimbus.casefile.facts import (
    build_facts,
    compute_priority,
    format_ddm,
    parse_ddm,
)
from nimbus.casefile.plan import plan_for
from nimbus.casefile.reach import geodesic_disk, reach_radius_km
from nimbus.casefile.recommend import recommendations
from nimbus.geo.reference import clip_to_sea

PHONE_OR_EMAIL = re.compile(
    r"(?:[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})|(?:\+\d[\d\s().-]{7,}\d)",
    re.I,
)


def test_ddm_round_trip():
    for lat, lon in ((56.90092, 11.90198), (56.72059, 11.87087), (-33.8688, 151.2093)):
        ddm = format_ddm(lat, lon)
        plat, plon = parse_ddm(ddm)
        assert abs(plat - lat) < 1e-5
        assert abs(plon - lon) < 1e-5


def test_search_box_contains_12kn_disk():
    facts = build_facts("D016", horizon_h=3)
    box = facts["search_area"]["search_box"]
    poly = shp_box(box["west"], box["south"], box["east"], box["north"])
    tgt = facts["target"]
    disk, _ = clip_to_sea(geodesic_disk(tgt["lat"], tgt["lon"], reach_radius_km(3, 12)))
    assert poly.contains(Point(tgt["lon"], tgt["lat"]))
    assert disk.within(poly.buffer(1e-4)) or poly.covers(disk)
    assert len(box["corners"]) == 4


def test_next_passes_systematic_first_and_rcm_access():
    facts = build_facts("D002")
    passes = facts["next_passes"]
    assert 1 <= len(passes) <= 5
    kinds = [p["coverage"] for p in passes]
    if "systematic" in kinds and "tasked" in kinds:
        last_sys = max(i for i, k in enumerate(kinds) if k == "systematic")
        first_tasked = min(i for i, k in enumerate(kinds) if k == "tasked")
        assert last_sys < first_tasked
    for item in passes:
        if item["family"] == "RCM":
            assert item["access"] != "open"
            assert item["access"] == "restricted"
    blob = json.dumps(facts)
    assert "Free data via Copernicus" not in blob
    row = match_row("D002")
    steps = recommendations(row, plan_for("D002"))
    assert all("Free data via Copernicus" not in (s.get("text") or "") for s in steps)


def test_priority_rule_synthetic():
    high = compute_priority(
        vessel_like=True, transient=True, ais_within_5km=False, mpa_inside_or_within_2km=True
    )
    med = compute_priority(
        vessel_like=True, transient=True, ais_within_5km=True, mpa_inside_or_within_2km=False
    )
    low = compute_priority(
        vessel_like=False, transient=True, ais_within_5km=False, mpa_inside_or_within_2km=True
    )
    assert high["tier"] == "HIGH"
    assert med["tier"] == "MEDIUM"
    assert low["tier"] == "LOW"


def test_facts_have_no_phone_or_email():
    for det_id in ("D002", "D016"):
        blob = json.dumps(build_facts(det_id))
        assert not PHONE_OR_EMAIL.search(blob)
        assert "dma.dk" in blob or "kustbevakningen.se" in blob
