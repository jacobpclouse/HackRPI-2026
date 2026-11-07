"""Preset ocean regions. The Kattegat box is the prepared Sentinel-1 scene."""

from __future__ import annotations

REGIONS = [
    {
        "id": "kattegat",
        "name": "Kattegat",
        "blurb": "Danish waters between Jutland and Sweden. Public AIS from the Danish Maritime Authority, and a real Sentinel-1 scene.",
        "lat": 56.90,
        "lon": 11.875,
        "bbox": [11.45, 56.60, 12.30, 57.20],
        "has_scene": True,
    },
    {
        "id": "gulf-of-guinea",
        "name": "Gulf of Guinea",
        "blurb": "Equatorial Atlantic, heavy commercial traffic. Coverage math only — no scene is packaged for this region.",
        "lat": 3.9,
        "lon": 2.4,
        "bbox": [1.4, 3.1, 3.4, 4.7],
        "has_scene": False,
    },
    {
        "id": "galapagos",
        "name": "Galápagos",
        "blurb": "Eastern Pacific around the Galápagos marine reserve. Coverage math only.",
        "lat": -0.4,
        "lon": -90.6,
        "bbox": [-91.8, -1.5, -89.4, 0.7],
        "has_scene": False,
    },
]


def by_id(region_id: str) -> dict | None:
    for region in REGIONS:
        if region["id"] == region_id:
            return region
    return None
