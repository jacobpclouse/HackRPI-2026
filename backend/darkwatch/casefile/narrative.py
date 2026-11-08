"""Guarded Gemini narrative for a vessel report and the incident brief.

Gemini REST fields verified 8 Nov 2026 against
https://ai.google.dev/gemini-api/docs/structured-output and the generateContent
reference: top-level ``systemInstruction`` (Content), ``contents``, and
``generationConfig`` with ``temperature``, ``responseMimeType`` =
``application/json``, and ``responseSchema`` (OpenAPI-subset schema). Endpoint
``generativelanguage.googleapis.com/v1beta/models/{model}:generateContent``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

from darkwatch import config, paths
from darkwatch.casefile.facts import MARKING, build_facts

log = logging.getLogger("darkwatch.narrative")

PROMPT_DIR = Path(__file__).with_name("prompts")
VESSEL_PROMPT = PROMPT_DIR / "vessel_report.txt"
BRIEF_PROMPT = PROMPT_DIR / "incident_brief.txt"
TIMEOUT_S = 30
BANNED = (
    "smuggler",
    "smuggling",
    "illegal",
    "illicit",
    "criminal",
    "crime",
    "guilty",
    "suspicious vessel",
    "pirate",
)
NUM_RE = re.compile(r"[-+]?(?:\d{1,3}(?:,\d{3})+)(?:\.\d+)?|[-+]?\d+(?:\.\d+)?")

# OpenAPI-subset schema for generationConfig.responseSchema (lowercase types).
VESSEL_SCHEMA = {
    "type": "object",
    "properties": {
        "bluf": {"type": "string"},
        "assessment": {"type": "string"},
        "evidence_readings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"item": {"type": "string"}, "reading": {"type": "string"}},
                "required": ["item", "reading"],
            },
        },
        "priority_rationale": {"type": "string"},
        "recommended_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"action_id": {"type": "string"}, "why": {"type": "string"}},
                "required": ["action_id", "why"],
            },
        },
        "alternative_explanations": {"type": "array", "items": {"type": "string"}},
        "confidence_statement": {"type": "string"},
    },
    "required": [
        "bluf",
        "assessment",
        "evidence_readings",
        "priority_rationale",
        "recommended_actions",
        "alternative_explanations",
        "confidence_statement",
    ],
}
BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "alternative_explanations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "alternative_explanations"],
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _prompt_text(path: Path) -> str:
    return path.read_text() if path.is_file() else ""


def _hashable_facts(facts: dict) -> dict:
    copy = json.loads(json.dumps(facts))
    if isinstance(copy.get("case"), dict):
        copy["case"].pop("generated_at", None)
    return copy


def cache_key(facts: dict, model: str, prompt: str) -> str:
    payload = json.dumps({"facts": _hashable_facts(facts), "model": model, "prompt": prompt}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _cache_path(det_id: str) -> Path:
    return paths.cache_dir() / "reports" / f"{det_id}.json"


def _read_cache(det_id: str, key: str) -> dict | None:
    path = _cache_path(det_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("key") != key:
        return None
    return data


def _write_cache(det_id: str, key: str, payload: dict) -> None:
    path = _cache_path(det_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"key": key, **payload}, indent=2))


def normalize_number(token: str) -> str:
    text = token.replace(",", "").strip()
    if text.startswith("+"):
        text = text[1:]
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("", "-", "+"):
        return "0"
    try:
        value = float(text)
    except ValueError:
        return text
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return format(value, "g")


def facts_numbers(facts: dict) -> tuple[set[str], list[float]]:
    blob = json.dumps(facts, ensure_ascii=False)
    tokens = {normalize_number(m.group(0)) for m in NUM_RE.finditer(blob)}
    values = []
    for tok in tokens:
        try:
            values.append(float(tok))
        except ValueError:
            continue
    return tokens, values


def extract_numbers(text: str) -> list[str]:
    return [m.group(0) for m in NUM_RE.finditer(text or "")]


def numbers_ok(text: str, facts: dict) -> tuple[bool, str | None]:
    tokens, values = facts_numbers(facts)
    for raw in extract_numbers(text):
        norm = normalize_number(raw)
        if norm in tokens:
            continue
        try:
            gem = float(raw.replace(",", ""))
        except ValueError:
            return False, f"unparseable number {raw!r}"
        decimals = len(raw.split(".")[-1]) if "." in raw else 0
        matched = False
        for fact in values:
            if abs(fact - gem) <= 1e-9:
                matched = True
                break
            if decimals == 0:
                if abs(round(fact) - gem) < 1e-9 and abs(fact - gem) < 0.5:
                    matched = True
                    break
            else:
                if abs(round(fact, decimals) - gem) < 10 ** (-decimals - 2) and abs(fact - gem) < 1.5 * 10 ** (-decimals):
                    matched = True
                    break
        if not matched:
            return False, f"invented number {raw!r}"
    return True, None


def _all_text(obj) -> str:
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return " ".join(_all_text(v) for v in obj.values())
    if isinstance(obj, list):
        return " ".join(_all_text(v) for v in obj)
    return ""


def banned_hit(text: str) -> str | None:
    low = (text or "").lower()
    for term in BANNED:
        if term in low:
            return term
    return None


def validate_vessel(narrative: dict, facts: dict) -> str | None:
    required = list(VESSEL_SCHEMA["required"])
    if not isinstance(narrative, dict):
        return "narrative is not an object"
    for key in required:
        if key not in narrative:
            return f"missing {key}"
    alts = narrative.get("alternative_explanations") or []
    if not isinstance(alts, list) or len(alts) < 2:
        return "need at least two alternative explanations"
    allowed = {a["id"] for a in facts.get("candidate_actions") or []}
    actions = narrative.get("recommended_actions") or []
    if not isinstance(actions, list):
        return "recommended_actions is not a list"
    for item in actions:
        aid = (item or {}).get("action_id")
        if aid not in allowed:
            return f"unknown action_id {aid!r}"
    blob = _all_text(narrative)
    hit = banned_hit(blob)
    if hit:
        return f"banned term {hit!r}"
    ok, reason = numbers_ok(blob, facts)
    if not ok:
        return reason
    return None


def validate_brief(narrative: dict, facts: dict) -> str | None:
    if not isinstance(narrative, dict) or "summary" not in narrative:
        return "missing summary"
    alts = narrative.get("alternative_explanations") or []
    if not isinstance(alts, list) or len(alts) < 2:
        return "need at least two alternative explanations"
    blob = _all_text(narrative)
    hit = banned_hit(blob)
    if hit:
        return f"banned term {hit!r}"
    ok, reason = numbers_ok(blob, facts)
    if not ok:
        return reason
    return None


def template_narrative(facts: dict) -> dict:
    case = facts.get("case") or {}
    tgt = facts.get("target") or {}
    ais = facts.get("ais_context") or {}
    pers = facts.get("persistence") or {}
    jur = facts.get("jurisdiction") or {}
    pri = facts.get("priority") or {}
    conf = tgt.get("confidence") or {}
    fp = tgt.get("footprint") or {}
    mpa = jur.get("protected_area") or {}
    best = facts.get("best_next") or {}
    shore = tgt.get("shore_km")
    shore_s = "an unknown distance from shore" if shore is None else f"{shore} km from shore"
    bluf = (
        f"{case.get('id')}: vessel-like radar return at {tgt.get('position_ddm')} "
        f"({shore_s}), priority {pri.get('tier')}. No public AIS match at acquisition."
    )
    location = "Inside" if mpa.get("in_mpa") else "Near" if mpa.get("near_mpa") else "Away from packaged protected areas"
    if mpa.get("name"):
        location = f"{location} {mpa.get('name')}" if location != "Away from packaged protected areas" else location
    country = jur.get("nearest_coast_country") or "an undetermined coast"
    assessment = (
        f"A radar return was recorded at {tgt.get('position_ddm')} on {case.get('acquisition_time_human')}. "
        f"Nearest coast is {country}. {location}. "
        f"Classifier score {conf.get('score')} (threshold {conf.get('threshold')}, tier {conf.get('tier')}). "
        f"Persistence {pers.get('verdict') or 'not reviewed'}. "
        f"{ais.get('summary') or ''} "
        f"Priority {pri.get('tier')} because {', '.join(pri.get('reasons') or [])}."
    )
    readings = [
        {"item": "AIS", "reading": ais.get("summary") or "No public AIS context."},
        {
            "item": "Classifier",
            "reading": (
                f"Score {conf.get('score')} against threshold {conf.get('threshold')} "
                f"({conf.get('tier')} confidence, vessel-like={conf.get('vessel_like')})."
            ),
        },
        {
            "item": "Persistence",
            "reading": f"Verdict {pers.get('verdict') or 'not reviewed'} on packaged passes.",
        },
        {
            "item": "Location",
            "reading": (
                f"{tgt.get('position_ddm')}; peak {tgt.get('peak_db')} dB; {shore_s}; "
                f"footprint {fp.get('length_m_range') or 'not measured'}."
            ),
        },
    ]
    actions = []
    for item in facts.get("candidate_actions") or []:
        actions.append({"action_id": item["id"], "why": item.get("title") or item["id"]})
        if len(actions) >= 5:
            break
    alts = [
        "Small vessels are not required to carry AIS.",
        "State vessels often do not broadcast, and reception can fail.",
    ]
    if best:
        conf_s = (
            f"Best next systematic pass is {best.get('satellite')} at {best.get('start')} "
            f"with {best.get('coverage_pct', {}).get('typical')} percent typical-speed coverage."
        )
    else:
        conf_s = "No systematic pass was marked as best next in the 48-hour plan."
    return {
        "bluf": bluf,
        "assessment": assessment.strip(),
        "evidence_readings": readings,
        "priority_rationale": f"Priority {pri.get('tier')}: {', '.join(pri.get('reasons') or ['rule did not fire'])}.",
        "recommended_actions": actions,
        "alternative_explanations": alts,
        "confidence_statement": conf_s,
    }


def template_brief(candidates: list[dict]) -> dict:
    bits = []
    for facts in candidates:
        case = facts.get("case") or {}
        tgt = facts.get("target") or {}
        pri = facts.get("priority") or {}
        bits.append(
            f"{case.get('id')} at {tgt.get('position_ddm')} priority {pri.get('tier')}"
        )
    listing = "; ".join(bits) if bits else "No dark candidates."
    return {
        "summary": (
            f"Kattegat dark candidates for verification: {listing}. "
            f"Marking {MARKING}. No public AIS is not evidence of wrongdoing."
        ),
        "alternative_explanations": [
            "Small vessels are not required to carry AIS.",
            "State vessels often do not broadcast, and reception can fail.",
        ],
    }


def _extract_text(payload: dict) -> str:
    return payload["candidates"][0]["content"]["parts"][0]["text"]


def _gemini_json(system: str, user: str, schema: dict) -> dict:
    """POST generateContent. Retry once on 5xx or invalid JSON."""
    key = config.gemini_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    model = config.gemini_model()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }
    last_err: Exception | None = None
    for _attempt in range(2):
        try:
            response = httpx.post(url, params={"key": key}, json=body, timeout=TIMEOUT_S)
            if response.status_code >= 500:
                last_err = RuntimeError(f"gemini {response.status_code}")
                continue
            response.raise_for_status()
            text = _extract_text(response.json()).strip()
            return json.loads(text)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            last_err = exc
            continue
    raise RuntimeError(str(last_err) if last_err else "gemini failed")


def _bundle(narrative: dict, provider: str, reason: str | None = None) -> dict:
    model = config.gemini_model()
    if provider == "gemini":
        line = f"Narrative: Gemini ({model}), generated {_now()}, checked against the facts"
    else:
        line = f"Narrative: template ({reason})" if reason else "Narrative: template"
    return {
        "narrative": narrative,
        "provenance": {
            "provider": provider,
            "model": model if provider == "gemini" else None,
            "generated_at": _now(),
            "reason": reason,
            "checked": provider == "gemini",
            "line": line,
        },
    }


def case_narrative(facts: dict, *, regenerate: bool = False) -> dict:
    prompt = _prompt_text(VESSEL_PROMPT)
    model = config.gemini_model()
    key = cache_key(facts, model, prompt)
    det_id = (facts.get("case") or {}).get("id") or "unknown"
    if not regenerate:
        hit = _read_cache(det_id, key)
        if hit and hit.get("narrative") and hit.get("provenance"):
            return {"narrative": hit["narrative"], "provenance": hit["provenance"]}
    fallback = template_narrative(facts)
    if not config.gemini_api_key():
        bundle = _bundle(fallback, "template", "GEMINI_API_KEY is not configured")
        _write_cache(det_id, key, bundle)
        return bundle
    try:
        parsed = _gemini_json(prompt, json.dumps(_hashable_facts(facts), ensure_ascii=False), VESSEL_SCHEMA)
    except Exception as exc:
        log.warning("gemini vessel call failed: %s", exc)
        bundle = _bundle(fallback, "template", str(exc))
        _write_cache(det_id, key, bundle)
        return bundle
    reason = validate_vessel(parsed, facts)
    if reason:
        log.warning("gemini vessel rejected: %s", reason)
        bundle = _bundle(fallback, "template", reason)
        _write_cache(det_id, key, bundle)
        return bundle
    bundle = _bundle(parsed, "gemini")
    _write_cache(det_id, key, bundle)
    return bundle


def brief_narrative(candidates: list[dict], *, regenerate: bool = False) -> dict:
    prompt = _prompt_text(BRIEF_PROMPT)
    model = config.gemini_model()
    combined = {"candidates": [_hashable_facts(f) for f in candidates], "marking": MARKING}
    key = cache_key(combined, model, prompt)
    if not regenerate:
        hit = _read_cache("brief", key)
        if hit and hit.get("narrative") and hit.get("provenance"):
            return {"narrative": hit["narrative"], "provenance": hit["provenance"]}
    fallback = template_brief(candidates)
    if not config.gemini_api_key():
        bundle = _bundle(fallback, "template", "GEMINI_API_KEY is not configured")
        _write_cache("brief", key, bundle)
        return bundle
    try:
        parsed = _gemini_json(prompt, json.dumps(combined, ensure_ascii=False), BRIEF_SCHEMA)
    except Exception as exc:
        log.warning("gemini brief call failed: %s", exc)
        bundle = _bundle(fallback, "template", str(exc))
        _write_cache("brief", key, bundle)
        return bundle
    reason = validate_brief(parsed, combined)
    if reason:
        log.warning("gemini brief rejected: %s", reason)
        bundle = _bundle(fallback, "template", reason)
        _write_cache("brief", key, bundle)
        return bundle
    bundle = _bundle(parsed, "gemini")
    _write_cache("brief", key, bundle)
    return bundle


def casefile_narrative(row: dict, scene: dict) -> dict:
    """Backward-compatible wrapper used by older assemble callers."""
    facts = build_facts(row["id"])
    bundle = case_narrative(facts)
    text = (bundle.get("narrative") or {}).get("bluf") or ""
    return {
        "provider": bundle["provenance"]["provider"],
        "model": bundle["provenance"].get("model"),
        "text": text,
        "configured": bool(config.gemini_api_key()),
        "label": bundle["provenance"].get("line"),
    }
