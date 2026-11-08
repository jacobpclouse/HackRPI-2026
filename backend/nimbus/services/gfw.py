"""Optional comparison against Global Fishing Watch public SAR presence.

The v3 4Wings report API needs GFW_API_TOKEN. Without it the endpoint explains
that and returns our own detection count only.
"""

from __future__ import annotations

import httpx

from nimbus import config


def sar_presence_report(bbox: list[float], start_date: str, end_date: str, our_detections: int) -> dict:
    token = config.gfw_api_token()
    dataset = config.gfw_dataset()
    base = {
        "available": False,
        "dataset": dataset,
        "our_detections": our_detections,
        "bbox": bbox,
    }
    if not token:
        base["reason"] = "GFW_API_TOKEN is not set. Nimbus still shows its own CFAR detections."
        return base
    west, south, east, north = bbox
    ring = [
        [west, south],
        [east, south],
        [east, north],
        [west, north],
        [west, south],
    ]
    url = "https://gateway.api.globalfishingwatch.org/v3/4wings/report"
    params = {
        "spatial-resolution": "HIGH",
        "temporal-resolution": "DAILY",
        "group-by": "VESSEL_ID",
        "datasets[0]": dataset,
        "date-range": f"{start_date},{end_date}",
        "format": "JSON",
    }
    try:
        response = httpx.post(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"geojson": {"type": "Polygon", "coordinates": [ring]}},
            timeout=45,
        )
        body_text = response.text[:4000]
        if response.status_code >= 400:
            return {
                **base,
                "available": False,
                "status": response.status_code,
                "reason": "Global Fishing Watch rejected the report request",
                "body": body_text,
            }
        data = response.json()
        entries = data.get("entries") or data.get("items") or []
        return {
            **base,
            "available": True,
            "status": response.status_code,
            "entry_count": len(entries) if isinstance(entries, list) else None,
            "response_keys": list(data.keys())[:12],
            "note": (
                "GFW public SAR presence is an independent product. "
                "A different count is expected: different scenes, detectors, and filters. "
                "This is a sanity check, not a score."
            ),
        }
    except Exception as exc:
        return {**base, "available": False, "reason": str(exc)}
