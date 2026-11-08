"""Optional outside services: Gemini briefs, Fish Audio narration, Global Fishing Watch, evidence."""

from nimbus.services.briefs import TEMPLATE_RULE, gemini_brief, template_brief
from nimbus.services.evidence import (
    ais_context,
    candidate_status,
    enrich_match,
    evidence_payload,
    model_payload,
    review_block,
)
from nimbus.services.gfw import sar_presence_report
from nimbus.services.narration import (
    DEFAULT_MODEL,
    DEFAULT_VOICE_ID,
    audio_dir,
    audio_filename,
    script_for,
    synthesize,
)

__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_VOICE_ID",
    "TEMPLATE_RULE",
    "ais_context",
    "audio_dir",
    "audio_filename",
    "candidate_status",
    "enrich_match",
    "evidence_payload",
    "gemini_brief",
    "model_payload",
    "review_block",
    "sar_presence_report",
    "script_for",
    "synthesize",
    "template_brief",
]
