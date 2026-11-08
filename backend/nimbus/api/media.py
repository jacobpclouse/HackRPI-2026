"""/api/briefs/{id}, /api/narrate, and generated narration audio."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from nimbus.api.common import matches, scene_summary
from nimbus.services import audio_dir, gemini_brief, script_for, synthesize

router = APIRouter()


@router.get("/api/briefs/{det_id}")
def brief(det_id: str):
    summary = scene_summary() or {}
    row = next((r for r in matches() if r["id"] == det_id), None)
    if row is None:
        raise HTTPException(404, "Unknown detection")
    if row.get("matched"):
        return {
            "provider": "template",
            "text": (
                f"{det_id} matches public AIS {row.get('name') or row.get('mmsi')} "
                f"at {row.get('match_km')} km. It is not an unmatched detection."
            ),
        }
    return gemini_brief(row, summary)


@router.post("/api/narrate")
def narrate(which: str = "opening", det_id: str | None = None):
    text = script_for("opening")
    key = "opening"
    if which == "candidate" and det_id:
        summary = scene_summary() or {}
        row = next((r for r in matches() if r["id"] == det_id), None)
        if row is None:
            raise HTTPException(404, "Unknown detection")
        text = gemini_brief(row, summary)["text"]
        key = f"candidate-{det_id}"
    result = synthesize(key, text)
    result["text"] = text
    return result


@router.get("/api/narration/{name}")
def narration_file(name: str):
    if "/" in name or not name.endswith(".mp3"):
        raise HTTPException(400, "Bad audio name")
    path = audio_dir() / name
    if not path.exists():
        raise HTTPException(404, "Audio not generated")
    return FileResponse(path, media_type="audio/mpeg")
