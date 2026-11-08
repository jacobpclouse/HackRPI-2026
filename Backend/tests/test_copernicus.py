from datetime import datetime, timezone

import httpx
from fastapi.testclient import TestClient

from darkwatch.api import create_app
from darkwatch.services import copernicus

SCENE = {
    "start": "2026-11-02T05:23:30Z",
    "end": "2026-11-02T05:24:02Z",
    "bbox": [11.45, 56.6, 12.3, 57.2],
    "scene_time": "2026-11-02T05:23:46Z",
}


def _off(monkeypatch):
    monkeypatch.setattr("darkwatch.config.cdse_client_id", lambda: "")
    monkeypatch.setattr("darkwatch.config.cdse_client_secret", lambda: "")


def test_status_is_unconfigured_without_secrets(monkeypatch):
    _off(monkeypatch)
    client = TestClient(create_app())
    response = client.get("/api/copernicus/status")
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is False
    assert body["state"] == "unconfigured"
    assert "CDSE_CLIENT_ID" in body["message"]
    assert "chat" in body["message"]


def test_status_does_not_echo_the_secret(monkeypatch):
    monkeypatch.setattr("darkwatch.config.cdse_client_id", lambda: "client-example")
    monkeypatch.setattr("darkwatch.config.cdse_client_secret", lambda: "secret-example")
    client = TestClient(create_app())
    response = client.get("/api/copernicus/status")
    assert response.json()["configured"] is True
    assert "secret-example" not in response.text
    assert "client-example" not in response.text


def test_unconfigured_search_does_not_invent_scenes(monkeypatch):
    _off(monkeypatch)
    client = TestClient(create_app())
    response = client.post(
        "/api/copernicus/acquisitions",
        json={
            "west": 103.5,
            "south": 1.0,
            "east": 104.0,
            "north": 1.4,
            "start": "2026-11-03T00:00:00Z",
            "end": "2026-11-03T23:59:59Z",
        },
    )
    body = response.json()
    assert body["state"] == "unconfigured"
    assert body["acquisitions"] == []


def test_visualizations_follow_reported_polarization():
    assert [row["id"] for row in copernicus.visualizations_for("DV")] == ["VV", "VH", "VVVH"]
    assert [row["id"] for row in copernicus.visualizations_for("SH")] == ["HH"]
    assert copernicus.visualizations_for("") == []
    assert copernicus.default_visualization("DV") == "VV"
    props = {"sar:polarizations": ["VV", "VH"]}
    assert copernicus.polarization_code(props) == "DV"


def test_process_request_is_gamma0_decibel_not_a_browser_layer():
    start = datetime(2026, 11, 3, tzinfo=timezone.utc)
    end = datetime(2026, 11, 3, 0, 0, 30, tzinfo=timezone.utc)
    body = copernicus.process_request((103.5, 1.0, 104.0, 1.4), start, end, "DV", "VV", "DESCENDING", 8)
    assert "IW-DV-VV-DECIBEL" not in str(body)
    data = body["input"]["data"][0]
    assert data["type"] == "sentinel-1-grd"
    assert data["processing"]["backCoeff"] == "GAMMA0_ELLIPSOID"
    assert data["processing"]["orthorectify"] == "true"
    assert data["dataFilter"]["resolution"] == "MEDIUM"
    assert data["dataFilter"]["orbitDirection"] == "DESCENDING"
    assert "0.21714724095" in body["evalscript"]
    assert "dataMask" in body["evalscript"]
    close = copernicus.process_request((0, 0, 1, 1), start, end, "DV", "VH", None, 12)
    assert close["input"]["data"][0]["dataFilter"]["resolution"] == "HIGH"
    width, height = copernicus.view_size(103.6, 1.15, 104.05, 1.45)
    assert max(width, height) == 640
    assert min(width, height) >= 64
    framed = copernicus.process_request((103.6, 1.15, 104.05, 1.45), start, end, "DV", "VV", None, 8, width, height)
    assert framed["output"]["width"] == width
    assert framed["output"]["height"] == height


def test_ships_only_when_the_packaged_scene_matches():
    match = copernicus.historical_ships(
        {"datetime": "2026-11-02T05:23:50Z", "bbox": [11.0, 56.0, 13.0, 58.0]},
        SCENE,
    )
    assert match["available"] is True
    assert "not live ships" in match["note"]
    assert "Red points" in match["note"]
    other_day = copernicus.historical_ships(
        {"datetime": "2026-11-03T05:23:50Z", "bbox": [11.0, 56.0, 13.0, 58.0]},
        SCENE,
    )
    other_place = copernicus.historical_ships(
        {"datetime": "2026-11-02T05:23:50Z", "bbox": [103.5, 1.0, 104.0, 1.4]},
        SCENE,
    )
    assert other_day["available"] is False
    assert other_place["available"] is False
    assert "not shown" in other_place["note"]


def test_catalog_feature_keeps_iw_and_drops_other_modes():
    feature = {
        "id": "S1A_IW",
        "bbox": [11.2, 56.4, 12.5, 57.4],
        "properties": {
            "datetime": "2026-11-02T05:23:48Z",
            "start_datetime": "2026-11-02T05:23:30Z",
            "end_datetime": "2026-11-02T05:24:02Z",
            "sar:instrument_mode": "IW",
            "s1:polarization": "DV",
            "platform": "sentinel-1a",
            "sat:orbit_state": "DESCENDING",
        },
    }
    row = copernicus._normalize_feature(feature, SCENE)
    assert row["polarization"] == "DV"
    assert row["ships"]["available"] is True
    assert row["orbit"] == "descending"
    other = dict(feature, properties={**feature["properties"], "sar:instrument_mode": "EW"})
    assert copernicus._normalize_feature(other, SCENE) is None


def test_tile_bbox_and_blank_png():
    west, south, east, north = copernicus.tile_bbox(0, 0, 0)
    assert west == -180
    assert east == 180
    assert north > 80
    assert south < -80
    assert copernicus.transparent_png().startswith(b"\x89PNG")


def test_upstream_message_strips_the_secret():
    response = httpx.Response(401, json={"error": {"message": "bad secret-example token"}})
    message = copernicus._safe_message(response, "secret-example")
    assert "secret-example" not in message
