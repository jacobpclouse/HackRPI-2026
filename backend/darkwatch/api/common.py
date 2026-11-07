"""Helpers shared by the routers: the active store and demo-file fallbacks."""

from __future__ import annotations

import json

from darkwatch import paths
from darkwatch.storage import get_snapshot, open_store

_store = None


def store():
    global _store
    if _store is None or not _store.ready():
        _store = open_store()
    return _store


def read_demo_json(name: str):
    path = paths.demo_dir() / name
    if not path.exists():
        return None
    return json.loads(path.read_text())


def scene_summary() -> dict | None:
    try:
        return get_snapshot().summary
    except Exception:
        return read_demo_json("summary.json")


def matches() -> list[dict]:
    try:
        return get_snapshot().matches
    except Exception:
        return read_demo_json("matches.json") or []


def split_families(families: str | None) -> list[str] | None:
    return [f.strip() for f in families.split(",") if f.strip()] if families else None
