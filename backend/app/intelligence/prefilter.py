"""
Cheap gate in front of Gemini. Most sensor events are obviously mundane —
sending those to an LLM wastes quota and latency. Only events with real
signal go through AI; everything else uses the deterministic fallback
directly, which is still a real detector (see fallback.py).
"""

from typing import Any

from app.core.config import (
    PREFILTER_MIN_ACCEL_PEAK,
    PREFILTER_MIN_GYRO_PEAK,
    PREFILTER_MIN_PHONE_CONFIDENCE,
)


def is_interesting(
    phone_confidence: float | None,
    features: dict[str, Any] | None,
) -> bool:
    features = features or {}
    accel_peak = float(features.get("accel_peak", 0) or 0)
    gyro_peak = float(features.get("gyro_peak", 0) or 0)
    phone_confidence = phone_confidence or 0.0

    if accel_peak >= PREFILTER_MIN_ACCEL_PEAK:
        return True
    if gyro_peak >= PREFILTER_MIN_GYRO_PEAK:
        return True
    if phone_confidence >= PREFILTER_MIN_PHONE_CONFIDENCE:
        return True

    return False
