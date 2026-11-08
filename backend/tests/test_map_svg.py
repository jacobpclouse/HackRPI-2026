"""Server-rendered report map."""

import xml.etree.ElementTree as ET

from nimbus.casefile import map_svg as map_mod
from nimbus.casefile.facts import build_facts
from nimbus.casefile.map_svg import render_map


def test_svg_has_scale_and_north():
    facts = build_facts("D016")
    svg = render_map(facts)
    root = ET.fromstring(svg)
    ids = {child.get("id") for child in root}
    assert "scale" in ids
    assert "north" in ids
    assert root.tag.endswith("svg")


def test_svg_renders_without_reference_layers(monkeypatch):
    facts = build_facts("D002")
    monkeypatch.setattr(map_mod, "load_land", lambda: None)
    monkeypatch.setattr(map_mod, "load_countries", lambda: None)
    monkeypatch.setattr(map_mod, "load_ports", lambda: None)
    svg = render_map(facts)
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert "reference layer unavailable" in svg
    assert "scale" in {child.get("id") for child in root}
    assert "north" in {child.get("id") for child in root}
