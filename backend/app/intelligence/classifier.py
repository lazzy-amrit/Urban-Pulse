"""
Gemini refinement step. Runs only in the background (see websocket/device.py)
— never in the synchronous ack path. Returns None whenever Gemini shouldn't
or can't be used right now; the caller keeps the fast fallback result.
"""

import logging
from typing import Any

from pydantic import ValidationError

from app.intelligence import ai_provider
from app.intelligence.ai_provider import AIInterpretation, RateLimited
from app.intelligence.prefilter import is_interesting
from app.intelligence.prompts import build_sensor_event_prompt

logger = logging.getLogger("urban_pulse.intelligence")

stats = {"gemini_calls": 0, "gemini_success": 0, "gemini_429": 0, "gemini_error": 0, "fallback_used": 0, "skipped_uninteresting": 0}


async def refine_with_gemini(
    event_type: str,
    phone_confidence: float | None,
    phone_severity: float | None,
    sensor_source: str | None,
    features: dict[str, Any] | None,
    speed: float | None,
    heading: float | None,
    prior_report_count: int,
    prior_unique_device_count: int,
    vision_evidence: list[dict[str, Any]] | None = None,
) -> AIInterpretation | None:
    if not ai_provider.is_configured():
        return None

    if not is_interesting(phone_confidence, features):
        stats["skipped_uninteresting"] += 1
        return None

    prompt = build_sensor_event_prompt(
        event_type=event_type,
        phone_confidence=phone_confidence,
        phone_severity=phone_severity,
        sensor_source=sensor_source,
        features=features,
        speed=speed,
        heading=heading,
        prior_report_count=prior_report_count,
        prior_unique_device_count=prior_unique_device_count,
        vision_evidence=vision_evidence,
    )

    stats["gemini_calls"] += 1
    try:
        result = await ai_provider.analyze_sensor_event(prompt)
        stats["gemini_success"] += 1
        return result
    except RateLimited:
        stats["gemini_429"] += 1
        logger.info("Gemini rate-limited; keeping fallback result for this event")
    except (ValidationError, ValueError) as exc:
        stats["gemini_error"] += 1
        logger.warning("Gemini returned malformed output: %s", exc)
    except Exception as exc:
        stats["gemini_error"] += 1
        logger.warning("Gemini call failed: %s", exc)

    return None
