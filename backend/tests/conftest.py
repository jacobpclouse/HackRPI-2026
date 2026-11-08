"""Test defaults: committed SAR catalog, no Gemini HTTP."""

from __future__ import annotations

import pytest

from darkwatch.catalog.source import read, snapshot_path


@pytest.fixture(autouse=True)
def _snapshot_catalog(monkeypatch):
    cat = read(snapshot_path(), origin="snapshot")
    monkeypatch.setattr("darkwatch.catalog.source._mem", cat)
    monkeypatch.setattr("darkwatch.catalog.source.fresh", lambda _cat: True)

    def _no_remote():
        raise RuntimeError("pytest uses the committed snapshot catalog")

    monkeypatch.setattr("darkwatch.catalog.source.fetch_remote", _no_remote)


@pytest.fixture(autouse=True)
def _no_gemini_network(monkeypatch):
    monkeypatch.setattr("darkwatch.config.gemini_api_key", lambda: "")
