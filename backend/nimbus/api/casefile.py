"""Reacquisition plans, authority-grade reports, and patrol exports."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from nimbus.casefile.assemble import brief_payload, casefile_payload
from nimbus.casefile.candidates import NotDarkCandidate, dark_ids
from nimbus.casefile.exports import export_bytes
from nimbus.casefile.facts import validate_horizon
from nimbus.casefile.map_svg import brief_map_svg, map_svg
from nimbus.casefile.plan import plan_for
from nimbus.casefile.reviews import add_review, all_latest, history, latest

router = APIRouter()

NOT_CANDIDATE = "Reacquisition plans and case files are generated only for Kattegat dark candidates."


class ReviewIn(BaseModel):
    analyst: str = Field(default="")
    decision: str = Field(default="")
    notes: str = Field(default="")


def _not_candidate() -> HTTPException:
    return HTTPException(404, NOT_CANDIDATE)


def _horizon(raw: float | None) -> float:
    try:
        return validate_horizon(raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/api/casefile")
def list_casefiles():
    ids = dark_ids()
    reviews = all_latest()
    return {"ids": ids, "reviews": {det_id: reviews.get(det_id) for det_id in ids}}


@router.get("/api/brief")
def incident_brief():
    return brief_payload()


@router.get("/api/brief/map.svg")
def incident_brief_map():
    payload = brief_payload()
    svg = brief_map_svg(payload["candidates"])
    return Response(svg, media_type="image/svg+xml")


@router.get("/api/casefile/{det_id}/plan")
def plan(det_id: str):
    try:
        return plan_for(det_id)
    except NotDarkCandidate:
        raise _not_candidate() from None


@router.get("/api/casefile/{det_id}/map.svg")
def case_map(det_id: str, horizon_h: float | None = Query(default=None)):
    try:
        svg = map_svg(det_id, _horizon(horizon_h))
    except NotDarkCandidate:
        raise _not_candidate() from None
    return Response(svg, media_type="image/svg+xml")


@router.get("/api/casefile/{det_id}/export.{fmt}")
def case_export(det_id: str, fmt: str, horizon_h: float | None = Query(default=None)):
    if fmt not in ("gpx", "kml", "geojson", "json"):
        raise HTTPException(404, "Export format must be gpx, kml, geojson, or json.")
    try:
        body, media, filename = export_bytes(det_id, fmt, _horizon(horizon_h))
    except NotDarkCandidate:
        raise _not_candidate() from None
    return Response(
        body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/api/casefile/{det_id}/narrative/regenerate")
def regenerate_narrative(det_id: str, horizon_h: float | None = Query(default=None)):
    try:
        return casefile_payload(det_id, horizon_h=_horizon(horizon_h), regenerate=True)
    except NotDarkCandidate:
        raise _not_candidate() from None


@router.get("/api/casefile/{det_id}")
def casefile(det_id: str, horizon_h: float | None = Query(default=None)):
    try:
        return casefile_payload(det_id, horizon_h=_horizon(horizon_h))
    except NotDarkCandidate:
        raise _not_candidate() from None


@router.get("/api/casefile/{det_id}/review")
def get_review(det_id: str):
    try:
        from nimbus.casefile.candidates import require_dark_candidate

        require_dark_candidate(det_id)
    except NotDarkCandidate:
        raise _not_candidate() from None
    return {"latest": latest(det_id), "history": history(det_id)}


@router.post("/api/casefile/{det_id}/review")
def post_review(det_id: str, body: ReviewIn):
    try:
        from nimbus.casefile.candidates import require_dark_candidate

        require_dark_candidate(det_id)
    except NotDarkCandidate:
        raise _not_candidate() from None
    try:
        entry = add_review(det_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return entry
