"""
Orchestrates AI interpretation of a sensor event, with guaranteed fallback.

This is the single entry point the rest of the app should call — it never
raises and never lets an AI provider failure crash the request.
"""

import logging
from typing import Any

from pydantic import ValidationError

from app.intelligence.ai_provider import AIInterpretation, get_ai_provider
from app.intelligence.fallback import fallback_interpret
from app.intelligence.prompts import build_sensor_event_prompt

logger = logging.getLogger("urban_pulse.intelligence")


def analyze_sensor_event(
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
) -> AIInterpretation:
    provider = get_ai_provider()

    if provider is None:
        return fallback_interpret(
            event_type=event_type,
            phone_confidence=phone_confidence,
            phone_severity=phone_severity,
            features=features,
            prior_report_count=prior_report_count,
            prior_unique_device_count=prior_unique_device_count,
        )

    try:
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
        result = provider.analyze_sensor_event(prompt)
        return result

    except (ValidationError, ValueError, KeyError) as exc:
        logger.warning("AI provider returned malformed response: %s", exc)
    except Exception as exc:  # noqa: BLE001 — any provider/network failure must not crash the app
        logger.warning("AI provider call failed: %s", exc)

    return fallback_interpret(
        event_type=event_type,
        phone_confidence=phone_confidence,
        phone_severity=phone_severity,
        features=features,
        prior_report_count=prior_report_count,
        prior_unique_device_count=prior_unique_device_count,
    )
