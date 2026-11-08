"""Evidence.json, candidate_status, AIS context, and /api/detections shape."""

import json

from fastapi.testclient import TestClient

from nimbus import paths
from nimbus.api import create_app
from nimbus.orbit.orbit import parse_time
from nimbus.services.evidence import ais_context, candidate_status, load


def _matches():
    return json.loads((paths.demo_dir() / "matches.json").read_text())


def test_evidence_json_covers_all_21_ids():
    payload = load()
    dets = payload["detections"]
    ids = [row["id"] for row in _matches()]
    assert len(ids) == 21
    assert set(dets) == set(ids)


def test_candidate_status_for_demo_ids():
    rows = {row["id"]: row for row in _matches()}
    ev = load()["detections"]
    assert candidate_status(rows["D002"], ev["D002"]) == "dark_candidate"
    assert candidate_status(rows["D016"], ev["D016"]) == "dark_candidate"
    assert candidate_status(rows["D021"], ev["D021"]) == "deprioritized"
    assert candidate_status(rows["D001"], ev["D001"]) == "matched"


def test_ais_context_d002_five_matched_vessels():
    rows = {row["id"]: row for row in _matches()}
    summary = json.loads((paths.demo_dir() / "summary.json").read_text())
    ctx = ais_context(rows["D002"], parse_time(summary["scene_time"]))
    vessels = ctx["vessels"]
    assert len(vessels) == 5, ctx["summary"]
    assert all(v.get("matched_detection") for v in vessels)
    assert all(v["matched_detection"] != "D002" for v in vessels)


def test_detections_api_keeps_original_matched_values():
    original = {row["id"]: row["matched"] for row in _matches()}
    client = TestClient(create_app())
    data = client.get("/api/detections").json()
    assert len(data["features"]) == 21
    for feature in data["features"]:
        props = feature["properties"]
        assert props["matched"] is original[props["id"]]
        assert "vessel_score" in props
        assert "candidate_status" in props
    assert sum(1 for f in data["features"] if f["properties"]["matched"]) == 18
