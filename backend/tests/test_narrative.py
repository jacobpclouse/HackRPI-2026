"""Guarded Gemini narrative: accept, reject, fallback, cache."""

import json

from nimbus.casefile import narrative as nar
from nimbus.casefile.facts import build_facts
from nimbus.casefile.narrative import case_narrative, template_narrative, validate_vessel


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
    monkeypatch.setattr("nimbus.config.gemini_api_key", lambda: "test-key")
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
    monkeypatch.setattr("nimbus.config.gemini_api_key", lambda: "test-key")
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
    monkeypatch.setattr("nimbus.config.gemini_api_key", lambda: "test-key")
    monkeypatch.setattr(nar.httpx, "post", lambda *_a, **_k: DummyResponse(_gemini_payload(bad)))
    bundle = case_narrative(facts, regenerate=True)
    assert bundle["provenance"]["provider"] == "template"
    assert "illegal" in (bundle["provenance"]["reason"] or "")


def test_unknown_action_id_rejected(monkeypatch, tmp_path):
    facts = build_facts("D016")
    bad = template_narrative(facts)
    bad["recommended_actions"] = [{"action_id": "board_ship", "why": "Go now."}]
    monkeypatch.setattr(nar, "_cache_path", lambda det_id: tmp_path / f"{det_id}.json")
    monkeypatch.setattr("nimbus.config.gemini_api_key", lambda: "test-key")
    monkeypatch.setattr(nar.httpx, "post", lambda *_a, **_k: DummyResponse(_gemini_payload(bad)))
    bundle = case_narrative(facts, regenerate=True)
    assert bundle["provenance"]["provider"] == "template"
    assert "action_id" in (bundle["provenance"]["reason"] or "")


def test_missing_key_uses_template(monkeypatch, tmp_path):
    facts = build_facts("D016")
    monkeypatch.setattr(nar, "_cache_path", lambda det_id: tmp_path / f"{det_id}.json")
    monkeypatch.setattr("nimbus.config.gemini_api_key", lambda: "")
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("httpx should not be called")

    monkeypatch.setattr(nar.httpx, "post", boom)
    bundle = case_narrative(facts, regenerate=True)
    assert bundle["provenance"]["provider"] == "template"
    assert called["n"] == 0
    assert "GEMINI_API_KEY" in (bundle["provenance"]["reason"] or "")


def test_stale_unconfigured_cache_is_ignored_once_key_exists(monkeypatch, tmp_path):
    facts = build_facts("D016")
    monkeypatch.setattr(nar, "_cache_path", lambda det_id: tmp_path / f"{det_id}.json")
    monkeypatch.setattr("nimbus.config.gemini_api_key", lambda: "")
    stale = case_narrative(facts, regenerate=True)
    assert stale["provenance"]["reason"] == "GEMINI_API_KEY is not configured"

    calls = {"n": 0}
    good = template_narrative(facts)

    def fake_post(*_a, **_k):
        calls["n"] += 1
        return DummyResponse(_gemini_payload(good))

    monkeypatch.setattr("nimbus.config.gemini_api_key", lambda: "test-key")
    monkeypatch.setattr(nar.httpx, "post", fake_post)
    bundle = case_narrative(facts, regenerate=False)
    assert calls["n"] == 1
    assert bundle["provenance"]["provider"] == "gemini"


def test_gemini_404_is_safe_and_does_not_embed_the_key(monkeypatch, tmp_path):
    facts = build_facts("D016")
    monkeypatch.setattr(nar, "_cache_path", lambda det_id: tmp_path / f"{det_id}.json")
    monkeypatch.setattr("nimbus.config.gemini_api_key", lambda: "secret-key-value")
    monkeypatch.setattr("nimbus.config.gemini_model", lambda: "gemini-2.5-flash")

    def fake_post(url, **kwargs):
        assert "key" not in (kwargs.get("params") or {})
        assert kwargs.get("headers", {}).get("x-goog-api-key") == "secret-key-value"
        return DummyResponse({}, status=404)

    monkeypatch.setattr(nar.httpx, "post", fake_post)
    bundle = case_narrative(facts, regenerate=True)
    reason = bundle["provenance"]["reason"] or ""
    assert bundle["provenance"]["provider"] == "template"
    assert "404" in reason or "not available" in reason
    assert "secret-key-value" not in reason
    assert "generativelanguage.googleapis.com" not in reason
