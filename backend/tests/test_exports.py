"""GPX and KML exports parse and carry the LKP, corners, and marking."""

import json
import xml.etree.ElementTree as ET

from darkwatch.casefile.exports import render_geojson, render_gpx, render_kml
from darkwatch.casefile.facts import MARKING, build_facts

GPX_NS = {"g": "http://www.topografix.com/GPX/1/1"}
KML_NS = {"k": "http://www.opengis.net/kml/2.2"}


def test_gpx_and_kml_parse():
    facts = build_facts("D016", horizon_h=3)
    gpx = ET.fromstring(render_gpx(facts))
    wpts = gpx.findall("g:wpt", GPX_NS)
    assert len(wpts) == 5
    names = [w.find("g:name", GPX_NS).text for w in wpts]
    assert any(n.startswith("LKP") for n in names)
    assert MARKING in ET.tostring(gpx, encoding="unicode")
    rtepts = gpx.findall("g:rte/g:rtept", GPX_NS)
    assert len(rtepts) == 5

    kml = ET.fromstring(render_kml(facts))
    blob = ET.tostring(kml, encoding="unicode")
    assert "LKP D016" in blob
    assert MARKING in blob
    assert blob.count("Polygon") >= 4


def test_geojson_has_lkp_and_box():
    facts = build_facts("D002")
    fc = render_geojson(facts)
    kinds = {f["properties"]["kind"] for f in fc["features"]}
    assert "lkp" in kinds
    assert "search_box" in kinds
    assert "reach" in kinds
    assert MARKING in json.dumps(fc, ensure_ascii=False)
