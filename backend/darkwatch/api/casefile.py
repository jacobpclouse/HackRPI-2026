"""Reacquisition plans and case files for Kattegat dark candidates."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from darkwatch.casefile.assemble import casefile_payload
from darkwatch.casefile.candidates import NotDarkCandidate, dark_ids
from darkwatch.casefile.plan import plan_for
from darkwatch.casefile.reviews import add_review, all_latest, history, latest

router = APIRouter()

NOT_CANDIDATE = "Reacquisition plans and case files are generated only for Kattegat dark candidates."


class ReviewIn(BaseModel):
    analyst: str = Field(default="")
    decision: str = Field(default="")
    notes: str = Field(default="")


def _not_candidate() -> HTTPException:
    return HTTPException(404, NOT_CANDIDATE)


@router.get("/api/casefile")
def list_casefiles():
    ids = dark_ids()
    reviews = all_latest()
    return {"ids": ids, "reviews": {det_id: reviews.get(det_id) for det_id in ids}}


@router.get("/api/casefile/{det_id}/plan")
def plan(det_id: str):
    try:
        return plan_for(det_id)
    except NotDarkCandidate:
        raise _not_candidate() from None


@router.get("/api/casefile/{det_id}")
def casefile(det_id: str):
    try:
        return casefile_payload(det_id)
    except NotDarkCandidate:
        raise _not_candidate() from None


@router.get("/api/casefile/{det_id}/review")
def get_review(det_id: str):
    try:
        from darkwatch.casefile.candidates import require_dark_candidate

        require_dark_candidate(det_id)
    except NotDarkCandidate:
        raise _not_candidate() from None
    return {"latest": latest(det_id), "history": history(det_id)}


@router.post("/api/casefile/{det_id}/review")
def post_review(det_id: str, body: ReviewIn):
    try:
        from darkwatch.casefile.candidates import require_dark_candidate

        require_dark_candidate(det_id)
    except NotDarkCandidate:
        raise _not_candidate() from None
    try:
        entry = add_review(det_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return entry
