"""Imagery API: samples, magic bytes, size limit."""

import pytest
from fastapi.testclient import TestClient

from nimbus import paths
from nimbus.api import create_app
from nimbus.detection import classifier

SAMPLES = paths.samples_dir()


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def test_wrong_magic_bytes_are_400(client):
    response = client.post(
        "/api/imagery/analyze",
        files={"image": ("x.png", b"this is not an image", "image/png")},
    )
    assert response.status_code == 400


def test_oversize_upload_is_413(client):
    payload = b"\xff\xd8\xff" + b"\x00" * (61 * 1024 * 1024)
    response = client.post(
        "/api/imagery/analyze",
        files={"image": ("big.jpg", payload, "image/jpeg")},
    )
    assert response.status_code == 413


@pytest.mark.skipif(not classifier.available(), reason="onnxruntime or model missing")
def test_samples_analyze(client):
    listed = client.get("/api/imagery/samples")
    assert listed.status_code == 200
    samples = listed.json()["samples"]
    assert samples
    jpeg = next(s for s in samples if s["type"] == "jpeg")
    geo = next(s for s in samples if s["type"] == "geotiff")
    jpg_res = client.post(f"/api/imagery/samples/{jpeg['name']}/analyze")
    assert jpg_res.status_code == 200
    body = jpg_res.json()
    assert body["detections"]
    assert "timings_ms" in body
    assert body.get("ais") in (None, {"available": False}) or body["ais"].get("available") is False
    assert body["kind"] in ("jpeg", "png")
    geo_res = client.post(f"/api/imagery/samples/{geo['name']}/analyze")
    assert geo_res.status_code == 200
    gbody = geo_res.json()
    assert gbody["ais"]["available"] is True
    assert gbody["ais"]["matched"] >= 1
    assert gbody["detections"]


def test_jpeg_has_no_ais_block_when_analyzed_as_bytes(client):
    jpg = next(SAMPLES.joinpath("lsssdd").glob("*.jpg"), None)
    if jpg is None:
        pytest.skip("no LS-SSDD sample")
    if not classifier.available():
        pytest.skip("classifier unavailable")
    response = client.post(
        "/api/imagery/analyze",
        files={"image": (jpg.name, jpg.read_bytes(), "image/jpeg")},
    )
    assert response.status_code == 200
    assert response.json().get("ais") in (None,) or response.json()["ais"] is None
