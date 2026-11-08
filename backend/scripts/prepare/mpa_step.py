"""Natura 2000 extract around the scene chip."""

from __future__ import annotations

import json

from nimbus.geo import fetch_natura2000, simplify_collection
from prepare import Target, log


def run(target: Target, *, force: bool = False) -> dict:
    mpa_path = target.out_dir / "mpas.geojson"
    if not force and mpa_path.exists():
        simple = json.loads(mpa_path.read_text())
        log(f"MPA polygons already present: {len(simple.get('features') or [])}")
        return simple
    log("fetching Natura 2000 sites for the chip")
    west, south, east, north = target.bbox
    raw = fetch_natura2000((west - 0.4, south - 0.4, east + 0.4, north + 0.4))
    simple = simplify_collection(raw)
    target.out_dir.mkdir(parents=True, exist_ok=True)
    mpa_path.write_text(json.dumps(simple))
    log(f"MPA polygons: {len(simple['features'])}")
    return simple
