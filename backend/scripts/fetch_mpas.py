#!/usr/bin/env python3
"""Fetch protected-area polygons for the demo regions.

Natura 2000 (EEA) is open and is what `make prepare` commits for the Kattegat.
WDPA / Protected Planet needs WDPA_API_TOKEN; without it this script prints
the exact request and leaves the bundled Natura 2000 sample in place.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from darkwatch import paths  # noqa: E402
from darkwatch.geo import REGIONS, fetch_natura2000, fetch_wdpa, simplify_collection  # noqa: E402
from darkwatch.geo.mpa import wdpa_token  # noqa: E402

logger = logging.getLogger("darkwatch.scripts")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = paths.demo_dir() / "mpas.geojson"
    region = next(r for r in REGIONS if r["id"] == "kattegat")
    west, south, east, north = region["bbox"]
    bbox = (west - 0.4, south - 0.4, east + 0.4, north + 0.4)
    logger.info("Natura 2000 bbox %s", bbox)
    fc = simplify_collection(fetch_natura2000(bbox))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fc))
    logger.info("wrote %d Natura 2000 features to %s", len(fc["features"]), out)
    token = wdpa_token()
    if not token:
        logger.info(
            "WDPA_API_TOKEN is unset. Protected Planet downloads require a free account "
            "token from https://api.protectedplanet.net/. The demo uses the EEA Natura 2000 "
            "subset above instead of a fabricated WDPA extract."
        )
        return
    wdpa = fetch_wdpa(bbox, token)
    wdpa_path = paths.raw_dir() / "wdpa_raw.json"
    wdpa_path.parent.mkdir(parents=True, exist_ok=True)
    wdpa_path.write_text(json.dumps(wdpa)[:2_000_000])
    logger.info("wrote WDPA response to %s", wdpa_path)


if __name__ == "__main__":
    main()
