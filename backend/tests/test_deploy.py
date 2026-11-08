import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nimbus.paths import MARKER, repo_root
from nimbus.services.narration import DEFAULT_MODEL, DEFAULT_VOICE_ID, audio_filename, synthesize
from nimbus.storage.live import get_snapshot, load_bundle, report_from_stored


def _fake_repo(base: Path) -> Path:
    root = base / "repo"
    (root / "data").mkdir(parents=True)
    (root / MARKER).touch()
    job = root / "backend" / "jobs"
    job.mkdir(parents=True)
    (job / "refresh.py").write_text("")
    return root


@pytest.fixture(autouse=True)
def _no_root_env(monkeypatch):
    monkeypatch.delenv("NIMBUS_ROOT", raising=False)


def test_repo_root_from_job_script_path(tmp_path):
    root = _fake_repo(tmp_path)
    found = repo_root(argv0="backend/jobs/refresh.py", cwd=root)
    assert found == root.resolve()


def test_repo_root_from_explicit_extra(tmp_path):
    root = _fake_repo(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    found = repo_root(argv0="", cwd=elsewhere, extra=str(root))
    assert found == root.resolve()


def test_repo_root_walks_up_from_cwd(tmp_path):
    root = _fake_repo(tmp_path)
    deep = root / "backend" / "jobs"
    assert repo_root(cwd=deep) == root.resolve()


def test_nimbus_root_env_wins(tmp_path, monkeypatch):
    first = _fake_repo(tmp_path / "a")
    second = _fake_repo(tmp_path / "b")
    monkeypatch.setenv("NIMBUS_ROOT", str(second))
    assert repo_root(cwd=first, extra=str(first)) == second.resolve()


def test_marker_without_data_is_not_a_root(tmp_path):
    lone = tmp_path / "lone"
    lone.mkdir()
    (lone / MARKER).touch()
    found = repo_root(cwd=lone)
    assert found != lone.resolve()
    assert (found / MARKER).is_file()


def test_bundle_snapshot_is_the_local_fallback():
    snap = load_bundle()
    assert snap.source == "bundle"
    assert snap.summary["detections"] == 21
    assert snap.summary["matched"] == 18
    assert len(snap.matches) == 21
    assert snap.tracks["type"] == "FeatureCollection"
    again = get_snapshot()
    assert again.source == "bundle"


def test_stored_passes_recompute_gaps():
    t0 = datetime(2026, 11, 2, tzinfo=timezone.utc)
    passes = [
        {
            "window_kind": "scene_day",
            "norad": 1,
            "name": "SENTINEL-1D",
            "family": "Sentinel-1",
            "coverage": "systematic",
            "start": "2026-11-02T05:23:22Z",
            "end": "2026-11-02T05:24:12Z",
            "center": "2026-11-02T05:23:47Z",
            "cross_km": 100,
            "alt_km": 700,
            "color": "#3DDCFF",
        }
    ]
    report = report_from_stored(passes, "scene_day", t0, t0 + timedelta(hours=24), None)
    assert report is not None
    assert report["systematic_pass_count"] == 1
    assert report["longest_gap"]["duration_s"] > 10 * 3600
    assert report_from_stored(passes, "upcoming", t0, t0 + timedelta(hours=1), None) is None


def test_narration_cache_and_default_voice(tmp_path, monkeypatch):
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "test-key")
    monkeypatch.delenv("FISH_AUDIO_VOICE_ID", raising=False)
    monkeypatch.delenv("FISH_AUDIO_MODEL", raising=False)
    text = "cache me"
    name = audio_filename("opening", text, DEFAULT_MODEL, DEFAULT_VOICE_ID)
    from nimbus.services import narration

    monkeypatch.setattr(narration, "AUDIO_DIR", tmp_path)
    (tmp_path / name).write_bytes(b"ID3" + b"x" * 200)
    result = synthesize("opening", text)
    assert result["cached"] is True
    assert result["voice_id"] == DEFAULT_VOICE_ID
    assert result["model"] == DEFAULT_MODEL
    assert result["audio_url"].endswith(name)
    assert os.environ["FISH_AUDIO_API_KEY"] == "test-key"
