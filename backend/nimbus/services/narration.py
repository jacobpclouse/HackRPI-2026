"""Fish Audio narration, with a text fallback when the key is unset.

Current API (https://docs.fish.audio/api-reference/endpoint/openapi-v1/text-to-speech):
POST https://api.fish.audio/v1/tts
Authorization: Bearer <key>
header model: s2.1-pro-free (free developer tier; s1 is deprecated and retires 2026-12-31)
JSON body: text, reference_id, format=mp3, prosody.speed

The default reference_id is Aria, a public English female voice used on
https://fish.audio/text-to-speech-api/ and listed as female in Fish's public
library. Set FISH_AUDIO_VOICE_ID to replace it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx

from nimbus import config, paths

# Free developer model. Unrecognized values fall back to s2.1-pro server-side.
DEFAULT_MODEL = config.DEFAULT_FISH_MODEL
# Aria — English, female. Public library id, not a private clone.
DEFAULT_VOICE_ID = config.DEFAULT_FISH_VOICE_ID
# Tests point this at a temp dir. None means data/cache/narration.
AUDIO_DIR: Path | None = None


def audio_dir() -> Path:
    return AUDIO_DIR or (paths.cache_dir() / "narration")

OPENING = (
    "Nimbus. Radar satellites do not watch the ocean all the time. "
    "This globe propagates public orbital elements for Sentinel-1, the RADARSAT Constellation, "
    "NISAR, ALOS, SAOCOM, and the commercial SAR fleets. "
    "Systematic missions are drawn as an approximate side-looking swath. "
    "ICEYE, Capella, and Umbra are marked possible coverage, because they image only when someone tasks them. "
    "Between passes, a patch of water can sit with no radar look for hours. That gap is computed from the orbits. "
    "We then open a real Sentinel-1 scene over the Kattegat and compare radar detections with Danish public AIS. "
    "Red marks are potential dark vessels: returns with no public AIS nearby. "
    "Unmatched means not matched to public AIS. It is not evidence of wrongdoing."
)


def script_for(which: str, extra: str = "") -> str:
    if which == "opening":
        return OPENING
    if which == "candidate" and extra:
        return extra
    return OPENING


def voice_id() -> str:
    return config.fish_audio_voice_id()


def model_name() -> str:
    return config.fish_audio_model()


def audio_filename(which: str, text: str, model: str, voice: str) -> str:
    digest = hashlib.sha256(f"{model}\n{voice}\n{text}".encode()).hexdigest()[:20]
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in which)[:40] or "clip"
    return f"{safe}-{digest}.mp3"


def synthesize(which: str, text: str) -> dict:
    key = config.fish_audio_api_key()
    voice = voice_id()
    model = model_name()
    filename = audio_filename(which, text, model, voice)
    payload = {
        "text": text,
        "audio_url": None,
        "provider": "none",
        "configured": bool(key),
        "voice_id": voice,
        "model": model,
        "cached": False,
    }
    if not key:
        payload["reason"] = (
            "FISH_AUDIO_API_KEY is not set. The default voice is Aria "
            f"({DEFAULT_VOICE_ID}); override it with FISH_AUDIO_VOICE_ID."
        )
        return payload
    folder = audio_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    if path.exists() and path.stat().st_size > 100:
        payload["provider"] = "fish"
        payload["audio_url"] = f"/api/narration/{filename}"
        payload["cached"] = True
        return payload
    try:
        response = httpx.post(
            "https://api.fish.audio/v1/tts",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "model": model,
            },
            json={
                "text": text,
                "reference_id": voice,
                "format": "mp3",
                "language": "en",
                "prosody": {"speed": 0.96},
            },
            timeout=90,
        )
        response.raise_for_status()
        path.write_bytes(response.content)
        payload["provider"] = "fish"
        payload["audio_url"] = f"/api/narration/{filename}"
        return payload
    except Exception as exc:
        payload["provider"] = "none"
        payload["error"] = str(exc)
        return payload
