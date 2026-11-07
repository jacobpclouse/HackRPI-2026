"""SAR mission families: name patterns, swath models, and exclusion rules.

Names are matched against whatever the GP query returns. A fixed NORAD list
is not the source of truth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Name rules applied only to objects the live catalog actually returned.
EXCLUDE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bDEB\b|\bR/B\b|DEBRIS", re.I), "debris or rocket body"),
    (
        re.compile(r"^SENTINEL-1B$", re.I),
        "Sentinel-1B is still catalogued but lost SAR imaging in December 2021",
    ),
]


@dataclass(frozen=True)
class FamilySpec:
    family: str
    coverage: str  # systematic | possible
    look: str  # right | either
    inc_near: float
    inc_far: float
    access_inc: float
    nominal_width_km: float | None
    color: str
    note: str


FAMILIES: list[tuple[re.Pattern[str], FamilySpec]] = [
    (
        re.compile(r"^SENTINEL-1[A-Z]$", re.I),
        FamilySpec(
            "Sentinel-1",
            "systematic",
            "right",
            29.1,
            46.0,
            46.0,
            None,
            "#3DDCFF",
            "Approximate Sentinel-1 IW swath, right-looking. Geometry is not an acquisition plan.",
        ),
    ),
    (
        re.compile(r"^RCM-\d+", re.I),
        FamilySpec(
            "RCM",
            "systematic",
            "right",
            20.0,
            49.0,
            49.0,
            None,
            "#7CFFB2",
            "Approximate RADARSAT Constellation wide swath, right-looking.",
        ),
    ),
    (
        re.compile(r"^RADARSAT-2$", re.I),
        FamilySpec(
            "RADARSAT-2",
            "possible",
            "either",
            20.0,
            49.0,
            50.0,
            100.0,
            "#B7F0C8",
            "Possible coverage. RADARSAT-2 is tasked; the strip is one ScanSAR-class example.",
        ),
    ),
    (
        re.compile(r"^NISAR$", re.I),
        FamilySpec(
            "NISAR",
            "systematic",
            "right",
            34.0,
            48.0,
            48.0,
            None,
            "#D6C2FF",
            "Approximate NISAR wide swath. Look side is modeled right-looking.",
        ),
    ),
    (
        re.compile(r"^ALOS-2$", re.I),
        FamilySpec(
            "ALOS-2",
            "systematic",
            "right",
            20.0,
            45.0,
            50.0,
            None,
            "#FFE08A",
            "Approximate ALOS-2 wide-swath geometry, right-looking.",
        ),
    ),
    (
        re.compile(r"^ALOS-4", re.I),
        FamilySpec(
            "ALOS-4",
            "systematic",
            "right",
            20.0,
            49.0,
            55.0,
            None,
            "#FFC14D",
            "Approximate ALOS-4 wide-swath geometry, right-looking.",
        ),
    ),
    (
        re.compile(r"^SAOCOM", re.I),
        FamilySpec(
            "SAOCOM",
            "systematic",
            "right",
            20.0,
            45.0,
            50.0,
            None,
            "#9BE7FF",
            "Approximate SAOCOM wide-swath geometry, right-looking.",
        ),
    ),
    (
        re.compile(r"^ICEYE", re.I),
        FamilySpec(
            "ICEYE",
            "possible",
            "either",
            15.0,
            45.0,
            50.0,
            30.0,
            "#FF9B6A",
            "Possible coverage. ICEYE is tasked on demand, not a continuous wide swath.",
        ),
    ),
    (
        re.compile(r"^CAPELLA", re.I),
        FamilySpec(
            "Capella",
            "possible",
            "either",
            15.0,
            45.0,
            50.0,
            15.0,
            "#FFD1A8",
            "Possible coverage. Capella is tasked on demand; the strip is a representative spotlight.",
        ),
    ),
    (
        re.compile(r"^UMBRA", re.I),
        FamilySpec(
            "Umbra",
            "possible",
            "either",
            15.0,
            45.0,
            50.0,
            15.0,
            "#F0A3FF",
            "Possible coverage. Umbra is tasked on demand; the strip is a representative spotlight.",
        ),
    ),
    (
        re.compile(r"^TERRASAR", re.I),
        FamilySpec(
            "TerraSAR-X",
            "possible",
            "right",
            15.0,
            45.0,
            55.0,
            30.0,
            "#C8D0DC",
            "Possible coverage. TerraSAR-X is tasked; strip is a representative stripmap.",
        ),
    ),
    (
        re.compile(r"^TANDEM", re.I),
        FamilySpec(
            "TanDEM-X",
            "possible",
            "right",
            15.0,
            45.0,
            55.0,
            30.0,
            "#AEB8C6",
            "Possible coverage. TanDEM-X is tasked; strip is a representative stripmap.",
        ),
    ),
    (
        re.compile(r"^PAZ$", re.I),
        FamilySpec(
            "PAZ",
            "possible",
            "right",
            15.0,
            45.0,
            55.0,
            30.0,
            "#9AA8B8",
            "Possible coverage. PAZ flies with TerraSAR-X and is tasked.",
        ),
    ),
    (
        re.compile(r"^COSMO-SKYMED|^CSG-", re.I),
        FamilySpec(
            "COSMO-SkyMed",
            "possible",
            "right",
            15.0,
            45.0,
            55.0,
            40.0,
            "#E7C4A0",
            "Possible coverage. COSMO-SkyMed (including CSG) is tasked.",
        ),
    ),
]

SYSTEMATIC_FAMILIES = [
    "Sentinel-1",
    "RCM",
    "NISAR",
    "ALOS-2",
    "ALOS-4",
    "SAOCOM",
]


def classify(name: str) -> FamilySpec | None:
    for pattern, spec in FAMILIES:
        if pattern.search(name.strip()):
            return spec
    return None


def exclusion_reason(name: str) -> str | None:
    for pattern, reason in EXCLUDE_RULES:
        if pattern.search(name.strip()):
            return reason
    return None
