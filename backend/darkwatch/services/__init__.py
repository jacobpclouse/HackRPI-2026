"""Optional outside services: Gemini briefs, Fish Audio narration, Global Fishing Watch."""

from darkwatch.services.briefs import TEMPLATE_RULE, gemini_brief, template_brief
from darkwatch.services.gfw import sar_presence_report
from darkwatch.services.narration import (
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
    "audio_dir",
    "audio_filename",
    "gemini_brief",
    "sar_presence_report",
    "script_for",
    "synthesize",
    "template_brief",
]
