"""Default: no Gemini HTTP in tests. Individual tests may re-enable a mock."""

import pytest


@pytest.fixture(autouse=True)
def _no_gemini_network(monkeypatch):
    monkeypatch.setattr("darkwatch.config.gemini_api_key", lambda: "")
