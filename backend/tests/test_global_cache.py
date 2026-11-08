"""Global AIS cache merge, accept-or-keep, atomic write, load fallbacks."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from darkwatch.ais import global_cache
from darkwatch.ais.stream import Ship

NOW = datetime(2026, 11, 7, 23, 0, tzinfo=timezone.utc)


def _ship(mmsi, lat, lon, category="other", minutes_ago=0):
    when = NOW - timedelta(minutes=minutes_ago)
    return Ship(
        mmsi=str(mmsi),
        name=str(mmsi),
        lat=lat,
        lon=lon,
        category=category,
        last_report=when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        has_position=True,
    )


def test_merge_overwrites_drops_old_and_scene_and_caps():
    bbox = global_cache.excluded_bbox()
    west, south, east, north = bbox
    previous = {
        "1": _ship("1", 10, 10, "other", minutes_ago=0),
        "2": _ship("2", 10, 11, "cargo", minutes_ago=5),
    }
    fresh = {
        "1": _ship("1", 10, 10.1, "other", minutes_ago=0),
        "old": _ship("old", 0.5, 0.5, "cargo", minutes_ago=13 * 60),
        "kat": _ship("kat", (south + north) / 2, (west + east) / 2, "tanker", minutes_ago=0),
        "3": _ship("3", -10, -10, "passenger", minutes_ago=1),
        "4": _ship("4", 20, 20, "fishing", minutes_ago=2),
        "5": _ship("5", 21, 21, "other", minutes_ago=3),
    }
    merged = global_cache.merge(previous, fresh, NOW, max_age_h=12, max_ships=3, bbox=bbox)
    assert "kat" not in merged
    assert "old" not in merged
    assert merged["1"].lon == 10.1
    assert set(merged) <= {"1", "2", "3", "4", "5"}
    assert len(merged) == 3
    cats = {s.category for s in merged.values()}
    assert "cargo" in cats or "passenger" in cats


def test_accept_or_keep():
    ok, reason = global_cache.should_accept(37, 37, 100)
    assert not ok
    assert "37" in reason
    ok, reason = global_cache.should_accept(800, 40, 100)
    assert not ok
    assert "50%" in reason
    ok, _ = global_cache.should_accept(800, 80, 100)
    assert ok


def test_atomic_write_keeps_old_on_failure(tmp_path, monkeypatch):
    dest = tmp_path / "ais_global.json"
    dest.write_text(json.dumps({"fetched_at": "old", "fields": [], "rows": []}))

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(global_cache.json, "dump", boom)
    with pytest.raises(OSError):
        global_cache.atomic_write(dest, {"fetched_at": "new", "fields": [], "rows": []})
    assert json.loads(dest.read_text())["fetched_at"] == "old"


def test_load_falls_back_to_seed_then_empty(tmp_path, monkeypatch):
    demo = tmp_path / "data" / "demo"
    cache = tmp_path / "data" / "cache"
    demo.mkdir(parents=True)
    cache.mkdir(parents=True)
    monkeypatch.setattr(global_cache.paths, "ais_global_cache", lambda: cache / "ais_global.json")
    monkeypatch.setattr(global_cache.paths, "ais_global_seed", lambda: demo / "ais_global_seed.json")
    monkeypatch.setattr(global_cache.paths, "demo_dir", lambda: demo)
    (demo / "scene_meta.json").write_text(json.dumps({"bbox": [11.45, 56.6, 12.3, 57.2]}))
    empty = global_cache.load()
    assert empty.source == "empty"
    assert empty.ships == {}
    seed_ship = _ship("99", 1, 2)
    payload = global_cache.to_payload(
        global_cache.CacheState(ships={"99": seed_ship}, fetched_at="2026-11-07T23:40:00Z", source="seed")
    )
    (demo / "ais_global_seed.json").write_text(json.dumps(payload))
    seeded = global_cache.load()
    assert seeded.source == "seed"
    assert "99" in seeded.ships
    (cache / "ais_global.json").write_text(
        json.dumps(
            global_cache.to_payload(
                global_cache.CacheState(
                    ships={"1": _ship("1", 3, 4)}, fetched_at="2026-11-07T23:50:00Z", source="live"
                )
            )
        )
    )
    cached = global_cache.load()
    assert cached.source == "cached"
    assert "1" in cached.ships
