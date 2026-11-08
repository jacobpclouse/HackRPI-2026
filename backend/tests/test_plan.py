"""Reacquisition plans for Kattegat dark candidates."""

from fastapi.testclient import TestClient

from nimbus.api import create_app
from nimbus.casefile.candidates import dark_ids
from nimbus.casefile.plan import plan_for


def test_dark_candidates_come_from_evidence_not_hardcoded_ids():
    ids = dark_ids()
    assert "D002" in ids
    assert "D016" in ids
    assert "D001" not in ids
    assert "D021" not in ids


def test_plan_has_systematic_pass_and_sort_order():
    for det_id in dark_ids():
        plan = plan_for(det_id)
        assert plan["horizon_h"] == 48
        systematic = [p for p in plan["passes"] if p["coverage"] == "systematic"]
        assert systematic, f"{det_id} should have a systematic pass within 48 h"
        centers = [p["center"] for p in systematic]
        assert centers == sorted(centers)
        tasked = [p for p in plan["passes"] if p["coverage"] == "tasked"]
        tasked_centers = [p["center"] for p in tasked]
        assert tasked_centers == sorted(tasked_centers)
        if systematic and tasked:
            last_sys = max(i for i, p in enumerate(plan["passes"]) if p["coverage"] == "systematic")
            first_tasked = min(i for i, p in enumerate(plan["passes"]) if p["coverage"] == "tasked")
            assert last_sys < first_tasked
        best = plan["best_next"]
        assert best is not None
        qualified = [
            p for p in systematic if p["coverage_frac"]["typical"] >= 0.5
        ]
        if qualified:
            assert best["coverage"] == "systematic"
            assert best["coverage_frac"]["typical"] >= 0.5
            assert best["center"] == min(p["center"] for p in qualified)
        else:
            assert best["coverage"] != "systematic" or best["coverage_frac"]["typical"] < 0.5
        for p in tasked:
            assert p["label"] == "possible, requires tasking"


def test_non_candidates_404():
    client = TestClient(create_app())
    for det_id in ("D001", "D021"):
        plan = client.get(f"/api/casefile/{det_id}/plan")
        assert plan.status_code == 404, det_id
        assert "dark candidates" in plan.json()["error"].lower()
        case = client.get(f"/api/casefile/{det_id}")
        assert case.status_code == 404, det_id
