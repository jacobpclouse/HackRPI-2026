"""Ships API: seed payload, no leaked key, AIS-only count."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from nimbus.ais.scene_layer import ais_only_vessels
from nimbus.api import create_app


def test_ais_only_count_is_interpolated_minus_matched():
    rows = ais_only_vessels()
    summary = json.loads((Path(__file__).resolve().parents[2] / "data" / "demo" / "summary.json").read_text())
    assert len(rows) == summary["ais_interpolated_for_match"] - summary["matched"]


def test_ships_global_and_no_key_leak(monkeypatch):
    monkeypatch.setenv("AISSTREAM_API_KEY", "dummy-aisstream-secret-xyz")
    monkeypatch.setenv("AIS_GLOBAL_REFRESH", "0")
    with TestClient(create_app()) as client:
        global_body = client.get("/api/ships/global")
        health = client.get("/api/health")
        config_js = client.get("/config.js")
        one = client.get("/api/ships/global/does-not-exist")
        blob = global_body.text + health.text + config_js.text + one.text
        assert "dummy-aisstream-secret-xyz" not in blob
        assert "AISSTREAM_API_KEY" not in blob
        data = global_body.json()
        assert "meta" in data
        assert data["meta"]["source"] in ("seed", "cached", "empty", "live")
        assert data["meta"]["refresh_enabled"] is False
        west, south, east, north = data["meta"]["excluded_bbox"]
        fields = data["fields"]
        lat_i, lon_i = fields.index("lat"), fields.index("lon")
        for row in data["rows"]:
            assert not (south <= row[lat_i] <= north and west <= row[lon_i] <= east)
        assert health.json()["ais_global"]["refresh_enabled"] is False
        ais_only = client.get("/api/scene/ais_only").json()
        summary = json.loads((Path(__file__).resolve().parents[2] / "data" / "demo" / "summary.json").read_text())
        assert len(ais_only["features"]) == summary["ais_interpolated_for_match"] - summary["matched"]
