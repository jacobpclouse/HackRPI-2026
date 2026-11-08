"""One payload for the printable case file and the incident brief."""

from __future__ import annotations

from datetime import datetime, timezone

from darkwatch.casefile.candidates import acquisition_time, dark_ids, require_dark_candidate, scene_block
from darkwatch.casefile.facts import DEFAULT_HORIZON_H, build_facts
from darkwatch.casefile.narrative import brief_narrative, case_narrative
from darkwatch.casefile.plan import plan_for
from darkwatch.casefile.recommend import LIMITS, recommendations, summary_line
from darkwatch.casefile.reviews import latest
from darkwatch.services.evidence import enrich_match, evidence_payload


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def casefile_payload(det_id: str, horizon_h: float = DEFAULT_HORIZON_H, regenerate: bool = False) -> dict:
    row = require_dark_candidate(det_id)
    scene = scene_block()
    t_acq = acquisition_time()
    plan = plan_for(det_id)
    facts = build_facts(det_id, horizon_h)
    bundle = case_narrative(facts, regenerate=regenerate)
    return {
        "facts": facts,
        "narrative": bundle["narrative"],
        "provenance": bundle["provenance"],
        "review": latest(det_id),
        "detection": enrich_match(row),
        "evidence": evidence_payload(row, t_acq),
        "plan": plan,
        "summary": summary_line(row),
        "recommendations": recommendations(row, plan),
        "limits": LIMITS,
        "scene": scene,
        "generated_at": facts["case"]["generated_at"],
    }


def brief_payload(regenerate: bool = False) -> dict:
    ids = dark_ids()
    candidates = [build_facts(det_id) for det_id in ids]
    bundle = brief_narrative(candidates, regenerate=regenerate)
    scene = scene_block()
    return {
        "scene": scene,
        "generated_at": _now(),
        "marking": (candidates[0]["case"]["marking"] if candidates else "UNVERIFIED · FOR VERIFICATION"),
        "candidates": candidates,
        "narrative": bundle["narrative"],
        "provenance": bundle["provenance"],
        "limits": LIMITS,
        "ids": ids,
    }
