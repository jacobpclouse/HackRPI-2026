"""Deterministic verification steps for a case file. No free-form model text."""

from __future__ import annotations

from darkwatch.catalog.missions import load_missions
from darkwatch.orbit.orbit import parse_time

LIMITS = (
    "No public AIS is not evidence of wrongdoing. Small vessels are not required to carry AIS, "
    "state vessels often do not broadcast, and reception can fail. Reach areas assume constant "
    "speed and ignore routing."
)

GFW_URL = "https://globalfishingwatch.org"


def summary_line(row: dict) -> str:
    parts = ["Vessel-like radar return with no public AIS at the time of the pass"]
    shore = row.get("shore_km")
    if shore is not None:
        parts.append(f"{float(shore):.0f} km offshore" if float(shore) >= 10 else f"{float(shore):.1f} km from shore")
    if row.get("in_mpa") and row.get("mpa_name"):
        parts.append(f"inside the {row['mpa_name']} protected area")
    elif row.get("near_mpa") and row.get("mpa_name"):
        dist = row.get("mpa_km")
        if dist is not None:
            parts.append(f"{float(dist):.1f} km from the {row['mpa_name']} protected area")
        else:
            parts.append(f"near the {row['mpa_name']} protected area")
    return ", ".join(parts) + "."


def _pct(frac: float) -> str:
    return f"{round(float(frac) * 100)}%"


def _mission_links(family: str) -> list[dict]:
    spec = load_missions().get(family) or {}
    return list(spec.get("links") or [])


def _operator(family: str) -> str:
    spec = load_missions().get(family) or {}
    return spec.get("operator") or family


def recommendations(row: dict, plan: dict) -> list[dict]:
    steps: list[dict] = []
    best = plan.get("best_next")
    if best and best.get("coverage") == "systematic":
        frac = (best.get("coverage_frac") or {}).get("typical") or 0
        family = best.get("family") or "systematic"
        when = best.get("center")
        steps.append(
            {
                "kind": "systematic",
                "text": (
                    f"Review the {family} pass at {when} ({_pct(frac)} of the typical-speed reach area). "
                    "Free data via Copernicus Browser or ASF Vertex."
                ),
                "links": _mission_links(family),
            }
        )
    t_acq = parse_time(plan["t_acq"])
    tasked = []
    for item in plan.get("passes") or []:
        if item.get("coverage") != "tasked":
            continue
        hours = (parse_time(item["center"]) - t_acq).total_seconds() / 3600.0
        if hours <= 24:
            tasked.append(item)
    if tasked:
        operators = sorted({_operator(item.get("family") or "") for item in tasked if _operator(item.get("family") or "")})
        who = ", ".join(operators[:3])
        if len(operators) > 3:
            who += " and others"
        steps.append(
            {
                "kind": "tasking",
                "text": f"Optional commercial tasking within 24 h ({who}).",
                "links": [],
            }
        )
    steps.append(
        {
            "kind": "gfw",
            "text": "Check Global Fishing Watch for vessel presence and AIS gaps.",
            "links": [{"label": "Global Fishing Watch", "url": GFW_URL}],
        }
    )
    if (row.get("in_mpa") or row.get("near_mpa")) and row.get("mpa_name"):
        steps.append(
            {
                "kind": "protected",
                "text": f"Compare against the management rules for {row['mpa_name']} (Natura 2000).",
                "links": [],
            }
        )
    steps.append(
        {
            "kind": "refer",
            "text": (
                "If verification supports it, refer to Denmark (Danish Maritime Authority) "
                "or Sweden (Swedish Coast Guard)."
            ),
            "links": [
                {"label": "Danish Maritime Authority", "url": "https://dma.dk"},
                {"label": "Swedish Coast Guard", "url": "https://www.kustbevakningen.se"},
            ],
        }
    )
    return steps
