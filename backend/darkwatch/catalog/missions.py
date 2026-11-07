"""Mission registry: who flies what, and where the imagery lives."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

from darkwatch.orbit.orbit import ensure_utc

REGISTRY_PATH = Path(__file__).with_name("missions.json")


@lru_cache(maxsize=1)
def load_missions() -> dict:
    return json.loads(REGISTRY_PATH.read_text())


def for_family(family: str) -> dict | None:
    return load_missions().get(family)


def copernicus_browser_url(lat: float, lon: float, when: datetime) -> str:
    """Deep link: Sentinel-1 IW VV, ±1 day around ``when``, centered on the point."""
    when = ensure_utc(when)
    start = (when - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00.000Z")
    end = (when + timedelta(days=1)).strftime("%Y-%m-%dT23:59:59.999Z")
    query = urlencode(
        {
            "zoom": "10",
            "lat": f"{lat:.5f}",
            "lng": f"{lon:.5f}",
            "datasetId": "S1_CDAS_IW_VVVH",
            "layerId": "IW-DV-VV-DECIBEL-GAMMA0-ORTHORECTIFIED",
            "fromTime": start,
            "toTime": end,
            "dateMode": "SINGLE",
        }
    )
    return f"https://browser.dataspace.copernicus.eu/?{query}"


def asf_vertex_url(lat: float, lon: float, when: datetime, dataset: str = "SENTINEL-1") -> str:
    """Vertex search link: dataset, date window, map centered on the point.

    ASF documents ``dataset``, ``start``, and ``end`` as URL parameters.
    ``center`` is the Vertex map hash convention (lon,lat).
    """
    when = ensure_utc(when)
    start = (when - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    end = (when + timedelta(days=1)).strftime("%Y-%m-%dT23:59:59Z")
    query = urlencode(
        {
            "dataset": dataset,
            "start": start,
            "end": end,
            "center": f"{lon:.5f},{lat:.5f}",
        }
    )
    return f"https://search.asf.alaska.edu/#/?{query}"


def deep_links(family: str, lat: float, lon: float, when: datetime) -> list[dict]:
    spec = for_family(family)
    if not spec or spec.get("deep_link") != "sentinel-1":
        return []
    return [
        {"label": "Copernicus Browser at this point", "url": copernicus_browser_url(lat, lon, when)},
        {"label": "ASF Vertex at this point", "url": asf_vertex_url(lat, lon, when)},
    ]
