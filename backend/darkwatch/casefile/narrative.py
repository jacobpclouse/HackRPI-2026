"""Optional case-file paragraph from the facts JSON only."""

from __future__ import annotations

import httpx

from darkwatch import config
from darkwatch.services.briefs import TEMPLATE_RULE, template_brief

NARRATIVE_LABEL = "Narrative generated from the facts above."


def casefile_narrative(row: dict, scene: dict) -> dict:
    text = template_brief(row, scene)
    key = config.gemini_api_key()
    if not key:
        return {
            "provider": "template",
            "text": text,
            "configured": False,
            "label": NARRATIVE_LABEL,
        }
    model = config.gemini_model()
    prompt = (
        "Rewrite the following maritime-awareness note as one short paragraph. "
        "Use only the facts given. Do not speculate about intent, nationality, or wrongdoing. "
        "Do not use the words smuggler, illegal, crime, or guilty. "
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
                "generationConfig": {"maxOutputTokens": 280, "temperature": 0.2},
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        rewritten = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if TEMPLATE_RULE not in rewritten:
            rewritten = rewritten.rstrip() + " " + TEMPLATE_RULE
        return {
            "provider": "gemini",
            "model": model,
            "text": rewritten,
            "configured": True,
            "label": NARRATIVE_LABEL,
        }
    except Exception as exc:
        return {
            "provider": "template",
            "text": text,
            "configured": True,
            "error": str(exc),
            "label": NARRATIVE_LABEL,
        }
