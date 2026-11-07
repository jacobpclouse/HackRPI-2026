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
    (
        re.compile(r"^RISAT-1$", re.I),
        "RISAT-1 stopped imaging after a 2017 power failure",
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
    (
        re.compile(r"KOMPSAT-5|ARIRANG-5", re.I),
        FamilySpec(
            "KOMPSAT-5",
            "possible",
            "right",
            20.0,
            45.0,
            50.0,
            30.0,
            "#5B8CFF",
            "Possible coverage. KOMPSAT-5 (Arirang-5) is tasked X-band.",
        ),
    ),
    (
        re.compile(r"^NOVASAR", re.I),
        FamilySpec(
            "NovaSAR",
            "possible",
            "either",
            15.0,
            45.0,
            50.0,
            50.0,
            "#FF6B9D",
            "Possible coverage. NovaSAR-1 is an S-band smallsat, tasked.",
        ),
    ),
    (
        re.compile(r"^RISAT-2B", re.I),
        FamilySpec(
            "RISAT-2",
            "possible",
            "either",
            15.0,
            45.0,
            50.0,
            30.0,
            "#FF5C8A",
            "Possible coverage. RISAT-2B class is tasked X-band.",
        ),
    ),
    (
        re.compile(r"^EOS-4$", re.I),
        FamilySpec(
            "EOS-04",
            "possible",
            "right",
            20.0,
            49.0,
            49.0,
            None,
            "#4DFFD2",
            "Possible coverage. EOS-04 is civil C-band; we have no acquisition plan so it does not close a gap.",
        ),
    ),
    (
        re.compile(r"^ASNARO-2$", re.I),
        FamilySpec(
            "ASNARO-2",
            "possible",
            "right",
            15.0,
            45.0,
            50.0,
            16.0,
            "#FF7A59",
            "Possible coverage. ASNARO-2 is tasked X-band. ASNARO-1 is optical and ignored.",
        ),
    ),
    (
        re.compile(r"^STRIX-", re.I),
        FamilySpec(
            "StriX",
            "possible",
            "either",
            15.0,
            45.0,
            50.0,
            20.0,
            "#A8FF4D",
            "Possible coverage. Synspective StriX is tasked X-band.",
        ),
    ),
    (
        re.compile(r"^QPS-SAR-", re.I),
        FamilySpec(
            "QPS-SAR",
            "possible",
            "either",
            15.0,
            45.0,
            50.0,
            20.0,
            "#4DC3FF",
            "Possible coverage. iQPS QPS-SAR is tasked X-band.",
        ),
    ),
    (
        re.compile(r"^GAOFEN-3(\s|$)", re.I),
        FamilySpec(
            "Gaofen-3",
            "possible",
            "right",
            20.0,
            50.0,
            50.0,
            None,
            "#FF4D6A",
            "Possible coverage. Gaofen-3 is civil C-band; no plan in this demo. Jilin-1 Gaofen optical birds are excluded.",
        ),
    ),
    (
        re.compile(r"^HAIYANG-3", re.I),
        FamilySpec(
            "Haiyang-3",
            "possible",
            "right",
            20.0,
            45.0,
            50.0,
            None,
            "#4D9FFF",
            "Possible coverage. Haiyang-3 is ocean C-band; no plan in this demo so it does not close a gap.",
        ),
    ),
    (
        re.compile(r"^PIESAT-", re.I),
        FamilySpec(
            "PIESAT",
            "possible",
            "either",
            15.0,
            45.0,
            50.0,
            20.0,
            "#C9FF4D",
            "Possible coverage. PIESAT (Hongtu) is a tasked interferometric X-band fleet.",
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
