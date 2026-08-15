"""
Final Urban Pulse confidence and severity calculation.

The backend is the sole authority on these numbers. Phone confidence and AI
confidence are both just inputs — neither is copied directly to the issue.

Everything here is deterministic and driven by named constants in
app/core/config.py so the formula can be tuned without touching logic.
"""

from app.core.config import (
    CONF_WEIGHT_PHONE,
    CONF_WEIGHT_AI,
    CONF_WEIGHT_EVENT_QUALITY,
    CONF_WEIGHT_INDEPENDENCE,
    CONF_WEIGHT_REPEAT,
    CONF_WEIGHT_SPATIAL,
    INDEPENDENCE_SATURATION_DEVICES,
    REPEAT_SATURATION_REPORTS,
    VISION_EVIDENCE_BOOST_MAX,
)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _saturating_factor(count: int, saturation_point: int) -> float:
    """
    Diminishing-returns curve: 0 at count=0, approaches 1.0 as count grows
    past `saturation_point`. Using 1 - 1/(1+count) style growth so extra
    reports from the same source keep contributing, but with less and less
    marginal effect.
    """
    if count <= 0:
        return 0.0
    return _clamp(count / (count + saturation_point))


def calculate_event_quality(phone_confidence: float | None, ai_confidence: float | None) -> float:
    phone_confidence = phone_confidence if phone_confidence is not None else 0.0
    ai_confidence = ai_confidence if ai_confidence is not None else 0.0
    return _clamp(
        CONF_WEIGHT_PHONE * phone_confidence + CONF_WEIGHT_AI * ai_confidence
    )


def calculate_independence_factor(unique_device_count: int) -> float:
    # A single device, no matter how many times it reports, cannot alone
    # generate strong "independence" evidence.
    if unique_device_count <= 1:
        return 0.0
    return _saturating_factor(unique_device_count - 1, INDEPENDENCE_SATURATION_DEVICES)


def calculate_repeat_factor(report_count: int) -> float:
    if report_count <= 1:
        return 0.0
    return _saturating_factor(report_count - 1, REPEAT_SATURATION_REPORTS)


def calculate_spatial_factor(matched_within_radius: bool) -> float:
    # Binary for now (clustering.py only returns matches within radius);
    # kept as its own factor so it's easy to make it continuous later
    # (e.g. tighter clustering -> higher factor).
    return 1.0 if matched_within_radius else 0.0


def calculate_final_confidence(
    phone_confidence: float | None,
    ai_confidence: float | None,
    report_count: int,
    unique_device_count: int,
    matched_within_radius: bool,
    vision_evidence_present: bool = False,
) -> float:
    event_quality = calculate_event_quality(phone_confidence, ai_confidence)
    independence_factor = calculate_independence_factor(unique_device_count)
    repeat_factor = calculate_repeat_factor(report_count)
    spatial_factor = calculate_spatial_factor(matched_within_radius)

    base = (
        CONF_WEIGHT_EVENT_QUALITY * event_quality
        + CONF_WEIGHT_INDEPENDENCE * independence_factor
        + CONF_WEIGHT_REPEAT * repeat_factor
        + CONF_WEIGHT_SPATIAL * spatial_factor
    )

    if vision_evidence_present:
        base += VISION_EVIDENCE_BOOST_MAX * event_quality

    return round(_clamp(base), 4)


def calculate_final_severity(
    ai_severity: float | None,
    phone_severity: float | None,
    report_count: int,
) -> float:
    ai_severity = ai_severity if ai_severity is not None else 0.0
    phone_severity = phone_severity if phone_severity is not None else 0.0

    # Severity reflects event intensity, not confidence — a single very
    # sharp impact can be severe even with low confidence.
    base_severity = _clamp(0.6 * ai_severity + 0.4 * phone_severity)

    # Repeated evidence nudges severity up slightly (same spot keeps hurting
    # cars), but with a small, capped influence so it never dominates.
    repeat_nudge = min(0.1, 0.02 * max(0, report_count - 1))

    return round(_clamp(base_severity + repeat_nudge), 4)
