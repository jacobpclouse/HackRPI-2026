"""Short briefs for unmatched detections.

GEMINI_API_KEY rewrites the local template in plain English. The template is
always the fallback, and the prompt forbids calling a detection a smuggler
or proof of illegality.
"""

from __future__ import annotations

import httpx

from darkwatch import config

TEMPLATE_RULE = (
    "Unmatched means not matched to public AIS. It is not evidence of wrongdoing."
)


def template_brief(det: dict, scene: dict) -> str:
    where = "inside" if det.get("in_mpa") else "near" if det.get("near_mpa") else "outside"
    mpa = det.get("mpa_name") or "no packaged protected area"
    dist = det.get("mpa_km")
    mpa_bit = f"{where} {mpa}" if det.get("mpa_name") else "away from the packaged protected areas"
    if dist is not None and not det.get("in_mpa"):
        mpa_bit += f" ({dist} km)"
    nearest = det.get("nearest_ais_km")
    if nearest is None:
        ais = "No public AIS position could be interpolated at acquisition time."
    else:
        ais = (
            f"The closest public AIS position was {nearest} km away"
            + (f" ({det.get('nearest_name') or det.get('nearest_mmsi')})." if det.get("nearest_mmsi") else ".")
        )
    return (
        f"{det.get('id')} is an unmatched radar return in {scene.get('scene_id')} "
        f"at {scene.get('scene_time')}, {det.get('lat'):.3f} N, {det.get('lon'):.3f} E. "
        f"CA-CFAR puts it {det.get('peak_db')} dB above the local sea, "
        f"{det.get('shore_km')} km from shore, {mpa_bit}. {ais} "
        f"Relative confidence {det.get('confidence')}. {TEMPLATE_RULE} "
        "Buoys, turbines, wakes, detector false alarms, and AIS reception gaps look the same."
    )


def gemini_brief(det: dict, scene: dict) -> dict:
    text = template_brief(det, scene)
    key = config.gemini_api_key()
    if not key:
        return {"provider": "template", "text": text, "configured": False}
    model = config.gemini_model()
    prompt = (
        "Rewrite the following maritime-awareness note in 4 short sentences. "
        "Do not use the words smuggler, illegal, crime, or guilty. "
        "Do not claim the detection is a vessel with certainty. "
        "Keep every number. End with the sentence: "
        f"'{TEMPLATE_RULE}'\n\n{text}"
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    try:
        response = httpx.post(
            url,
            params={"key": key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 280, "temperature": 0.3},
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        rewritten = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if TEMPLATE_RULE not in rewritten:
            rewritten = rewritten.rstrip() + " " + TEMPLATE_RULE
        return {"provider": "gemini", "model": model, "text": rewritten, "configured": True}
    except Exception as exc:
        return {"provider": "template", "text": text, "configured": True, "error": str(exc)}
