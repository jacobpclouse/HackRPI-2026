"""Guarded Gemini narrative: accept, reject, fallback, cache."""

import json

from darkwatch.casefile import narrative as nar
from darkwatch.casefile.facts import build_facts
from darkwatch.casefile.narrative import case_narrative, template_narrative, validate_vessel


class DummyResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise nar.httpx.HTTPStatusError("err", request=None, response=None)

    def json(self):
        return self._payload


def _gemini_payload(obj: dict) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}}]}


def test_valid_mocked_response_accepted(monkeypatch, tmp_path):
    facts = build_facts("D016")
    good = template_narrative(facts)
    calls = {"n": 0}

    def fake_post(*_a, **_k):
        calls["n"] += 1
        return DummyResponse(_gemini_payload(good))

    monkeypatch.setattr(nar, "_cache_path", lambda det_id: tmp_path / f"{det_id}.json")
    monkeypatch.setattr("darkwatch.config.gemini_api_key", lambda: "test-key")
    monkeypatch.setattr(nar.httpx, "post", fake_post)
    bundle = case_narrative(facts, regenerate=True)
    assert bundle["provenance"]["provider"] == "gemini"
    assert bundle["narrative"]["bluf"] == good["bluf"]
    assert calls["n"] == 1
    case_narrative(facts, regenerate=False)
    assert calls["n"] == 1


def test_invented_number_rejected(monkeypatch, tmp_path):
    facts = build_facts("D002")
    bad = template_narrative(facts)
    bad["bluf"] += " Displacement 777.77 tonnes."

    monkeypatch.setattr(nar, "_cache_path", lambda det_id: tmp_path / f"{det_id}.json")
    monkeypatch.setattr("darkwatch.config.gemini_api_key", lambda: "test-key")
    monkeypatch.setattr(nar.httpx, "post", lambda *_a, **_k: DummyResponse(_gemini_payload(bad)))
    bundle = case_narrative(facts, regenerate=True)
    assert bundle["provenance"]["provider"] == "template"
    assert "777.77" in (bundle["provenance"]["reason"] or "")
    assert validate_vessel(bad, facts)


def test_banned_word_rejected(monkeypatch, tmp_path):
    facts = build_facts("D002")
    bad = template_narrative(facts)
    bad["assessment"] = "This is an illegal vessel in the Kattegat."
    monkeypatch.setattr(nar, "_cache_path", lambda det_id: tmp_path / f"{det_id}.json")
    monkeypatch.setattr("darkwatch.config.gemini_api_key", lambda: "test-key")
    monkeypatch.setattr(nar.httpx, "post", lambda *_a, **_k: DummyResponse(_gemini_payload(bad)))
    bundle = case_narrative(facts, regenerate=True)
    assert bundle["provenance"]["provider"] == "template"
    assert "illegal" in (bundle["provenance"]["reason"] or "")


def test_unknown_action_id_rejected(monkeypatch, tmp_path):
    facts = build_facts("D016")
    bad = template_narrative(facts)
    bad["recommended_actions"] = [{"action_id": "board_ship", "why": "Go now."}]
    monkeypatch.setattr(nar, "_cache_path", lambda det_id: tmp_path / f"{det_id}.json")
    monkeypatch.setattr("darkwatch.config.gemini_api_key", lambda: "test-key")
    monkeypatch.setattr(nar.httpx, "post", lambda *_a, **_k: DummyResponse(_gemini_payload(bad)))
    bundle = case_narrative(facts, regenerate=True)
    assert bundle["provenance"]["provider"] == "template"
    assert "action_id" in (bundle["provenance"]["reason"] or "")


def test_missing_key_uses_template(monkeypatch, tmp_path):
    facts = build_facts("D016")
    monkeypatch.setattr(nar, "_cache_path", lambda det_id: tmp_path / f"{det_id}.json")
    monkeypatch.setattr("darkwatch.config.gemini_api_key", lambda: "")
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("httpx should not be called")

    monkeypatch.setattr(nar.httpx, "post", boom)
    bundle = case_narrative(facts, regenerate=True)
    assert bundle["provenance"]["provider"] == "template"
    assert called["n"] == 0
    assert "GEMINI_API_KEY" in (bundle["provenance"]["reason"] or "")
