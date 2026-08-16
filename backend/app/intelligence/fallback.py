"""
Deterministic rule-based interpretation. Used directly for uninteresting
events (see prefilter.py) and as the safety net when Gemini is unavailable,
rate-limited, or returns something malformed. Must never raise.
"""

from typing import Any

from app.intelligence.ai_provider import AIInterpretation

_SURFACE_IRREGULARITY_FLOOR = 0.5


def fallback_interpret(
    phone_confidence: float | None,
    phone_severity: float | None,
    speed: float | None,
    features: dict[str, Any] | None,
    prior_report_count: int,
    prior_unique_device_count: int,
) -> AIInterpretation:
    features = features or {}
    accel_peak = float(features.get("accel_peak", 0) or 0)
    gyro_peak = float(features.get("gyro_peak", 0) or 0)
    duration_ms = float(features.get("duration_ms", 0) or 0)
    phone_confidence = phone_confidence if phone_confidence is not None else 0.3
    phone_severity = phone_severity if phone_severity is not None else 0.3
    speed = speed or 0.0

    if accel_peak <= 0 and gyro_peak <= 0:
        return AIInterpretation(
            classification="unknown",
            confidence=min(0.2, phone_confidence),
            severity=phone_severity,
            reasoning_summary="No usable feature data.",
        )

    is_sharp_impact = accel_peak >= 2.0 and 0 < duration_ms <= 600
    has_gyro_support = gyro_peak >= 1.0
    is_rhythmic = 0.8 <= accel_peak < 2.0 and gyro_peak < 0.8 and speed >= 15
    has_repeat_support = prior_report_count >= 1
    has_independent_support = prior_unique_device_count >= 2

    confidence = 0.30
    if is_sharp_impact:
        confidence += 0.20
    elif is_rhythmic:
        confidence += 0.20
    elif accel_peak >= 1.2 or gyro_peak >= 0.6:
        confidence += 0.12

    if has_gyro_support:
        confidence += 0.10
    elif gyro_peak >= 0.4:
        confidence += 0.08

    if has_repeat_support:
        confidence += 0.10
    if has_independent_support:
        confidence += 0.15
    confidence = max(0.0, min(1.0, confidence))

    severity = max(0.0, min(1.0, accel_peak / 4.0))

    if is_sharp_impact and has_independent_support:
        classification = "pothole_likely"
    elif is_sharp_impact and has_gyro_support:
        classification = "impact_event"
    elif is_rhythmic:
        classification = "speed_bump_likely"
    elif accel_peak >= _SURFACE_IRREGULARITY_FLOOR or gyro_peak >= 0.4:
        classification = "surface_irregularity"
    else:
        classification = "road_anomaly"

    return AIInterpretation(
        classification=classification,
        confidence=confidence,
        severity=severity,
        reasoning_summary="Rule-based interpretation from sensor features.",
    )
