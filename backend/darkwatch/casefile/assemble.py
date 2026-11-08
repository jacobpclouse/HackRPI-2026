"""One payload for the printable case file."""

from __future__ import annotations

from datetime import datetime, timezone

from darkwatch.casefile.candidates import acquisition_time, require_dark_candidate, scene_block
from darkwatch.casefile.narrative import casefile_narrative
from darkwatch.casefile.plan import plan_for
from darkwatch.casefile.recommend import LIMITS, recommendations, summary_line
from darkwatch.casefile.reviews import latest
from darkwatch.services.evidence import enrich_match, evidence_payload


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def casefile_payload(det_id: str, include_narrative: bool = False) -> dict:
    row = require_dark_candidate(det_id)
    scene = scene_block()
    t_acq = acquisition_time()
    plan = plan_for(det_id)
    narrative = casefile_narrative(row, scene) if include_narrative else None
    return {
        "detection": enrich_match(row),
        "evidence": evidence_payload(row, t_acq),
        "plan": plan,
        "summary": summary_line(row),
        "recommendations": recommendations(row, plan),
        "narrative": narrative,
        "review": latest(det_id),
        "limits": LIMITS,
        "scene": scene,
        "generated_at": _now(),
    }
