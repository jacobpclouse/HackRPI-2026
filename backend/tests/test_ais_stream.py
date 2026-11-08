"""AISStream parser. No live WebSocket."""

import json
from pathlib import Path

from nimbus.ais.stream import category_for, parse_message

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "aisstream_messages.json").read_text())


def test_position_report_and_static_merge():
    ships = {}
    assert parse_message(FIXTURES["position"], ships) == "position"
    ship = ships["368207620"]
    assert ship.lat == 25.7617
    assert ship.lon == -80.1918
    assert ship.sog == 12.4
    assert ship.cog == 86.7
    assert ship.heading == 87
    assert parse_message(FIXTURES["static"], ships) == "static"
    assert ship.category == "cargo"
    assert ship.type_code == 70
    assert ship.destination == "ROTTERDAM"
    assert ship.length_m == 180


def test_missing_and_unavailable_coords_are_skipped():
    ships = {}
    assert parse_message(FIXTURES["missing_coords"], ships) is None
    assert parse_message(FIXTURES["unavailable"], ships) is None
    assert parse_message(FIXTURES["origin"], ships) is None
    assert ships == {}


def test_categories():
    assert category_for(70) == "cargo"
    assert category_for(80) == "tanker"
    assert category_for(60) == "passenger"
    assert category_for(30) == "fishing"
    assert category_for(31) == "tug"
    assert category_for(52) == "tug"
    assert category_for(35) == "military"
    assert category_for(36) == "pleasure"
    assert category_for(None) == "other"
    assert category_for(0) == "other"
