"""Case-file payload, recommendation rules, and review persistence."""

import pytest
from fastapi.testclient import TestClient

from darkwatch.api import create_app
from darkwatch.casefile import reviews as reviews_mod
from darkwatch.casefile.candidates import match_row
from darkwatch.casefile.plan import plan_for
from darkwatch.casefile.recommend import LIMITS, recommendations, summary_line


@pytest.fixture(autouse=True)
def _no_gemini(monkeypatch):
    monkeypatch.setattr("darkwatch.config.gemini_api_key", lambda: "")


def test_recommendations_include_protected_area_for_d016():
    row = match_row("D016")
    plan = plan_for("D016")
    steps = recommendations(row, plan)
    kinds = [s["kind"] for s in steps]
    assert "gfw" in kinds
    assert "refer" in kinds
    protected = [s for s in steps if s["kind"] == "protected"]
    assert protected
    assert "Lilla Middelgrund" in protected[0]["text"]
    assert "Natura 2000" in protected[0]["text"]
    best = plan.get("best_next")
    if best and best.get("coverage") == "systematic":
        assert any(s["kind"] == "systematic" for s in steps)


def test_limits_text_is_in_payload():
    client = TestClient(create_app())
    data = client.get("/api/casefile/D002").json()
    assert data["limits"] == LIMITS
    assert "No public AIS is not evidence of wrongdoing" in data["limits"]
    assert "D002" in data["summary"] or "offshore" in data["summary"]
    assert data["evidence"]["candidate_status"] == "dark_candidate"


def test_summary_line_is_deterministic():
    d016 = summary_line(match_row("D016"))
    assert "Lilla Middelgrund" in d016
    assert "24 km offshore" in d016
    d002 = summary_line(match_row("D002"))
    assert "no public AIS" in d002
    assert "smuggler" not in d002.lower()


def test_review_validation_and_history_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(reviews_mod, "REVIEW_PATH", tmp_path / "case_reviews.json")
    client = TestClient(create_app())

    missing_name = client.post("/api/casefile/D002/review", json={"analyst": "", "decision": "Verify further"})
    assert missing_name.status_code == 400

    dismiss = client.post(
        "/api/casefile/D002/review",
        json={"analyst": "Ada", "decision": "Dismiss", "notes": ""},
    )
    assert dismiss.status_code == 400

    refer = client.post(
        "/api/casefile/D002/review",
        json={"analyst": "Ada", "decision": "Refer", "notes": ""},
    )
    assert refer.status_code == 400

    first = client.post(
        "/api/casefile/D002/review",
        json={"analyst": "Ada", "decision": "Verify further", "notes": ""},
    )
    assert first.status_code == 200
    second = client.post(
        "/api/casefile/D002/review",
        json={"analyst": "Bea", "decision": "Refer", "notes": "Share with DMA"},
    )
    assert second.status_code == 200

    payload = client.get("/api/casefile/D002/review").json()
    assert payload["latest"]["analyst"] == "Bea"
    assert payload["latest"]["decision"] == "Refer"
    assert [row["analyst"] for row in payload["history"]] == ["Bea", "Ada"]

    case = client.get("/api/casefile/D002").json()
    assert case["review"]["decision"] == "Refer"
    assert case["review"]["analyst"] == "Bea"
    assert case["facts"]["case"]["id"] == "D002"
    assert case["narrative"]["bluf"]
    assert "gemini" in case["provenance"]["line"].lower() or "template" in case["provenance"]["line"].lower()


def test_export_and_map_and_health_fields():
    client = TestClient(create_app())
    gpx = client.get("/api/casefile/D016/export.gpx?horizon_h=3")
    assert gpx.status_code == 200
    assert b"LKP D016" in gpx.content
    svg = client.get("/api/casefile/D016/map.svg")
    assert svg.status_code == 200
    assert b'id="scale"' in svg.content
    health = client.get("/api/health").json()
    assert "ports" in health["reference"]
    assert "configured" in health["gemini"]
    assert "model" in health["gemini"]
    assert "key" not in health["gemini"]
