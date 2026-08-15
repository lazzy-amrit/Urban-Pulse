"""
Prompt construction for the AI interpretation step.

Kept isolated so prompt wording can be iterated on without touching
provider or classifier logic.
"""

import json
from typing import Any


SYSTEM_INSTRUCTIONS = """You are the evidence-interpretation layer for Urban Pulse, \
a road-anomaly detection system. You will be given sensor evidence from a single \
phone-reported event, plus context about prior reports near the same location.

Rules you MUST follow:
- A single observation does NOT prove a pothole or any confirmed road issue.
- Classify conservatively. Prefer "road_anomaly" or "unknown" when evidence is weak or ambiguous.
- Only lean toward "pothole_likely" or "speed_bump_likely" when the sensor signature is a strong match.
- Never invent measurements, GPS coordinates, or facts not present in the input.
- Never claim certainty that the evidence does not support.
- confidence and severity must each be a number between 0.0 and 1.0.
- Respond with JSON ONLY. No prose, no markdown fences, no explanation outside the JSON object.

Respond with exactly this JSON shape:
{"classification": "<one of: road_anomaly, surface_irregularity, impact_event, pothole_likely, speed_bump_likely, unknown>", \
"confidence": <0.0-1.0>, "severity": <0.0-1.0>, "reasoning_summary": "<one short sentence>"}
"""


def build_sensor_event_prompt(
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
) -> str:
    """Builds the full prompt (system instructions + structured evidence)."""

    evidence = {
        "phone_reported_event_type": event_type,
        "phone_confidence": phone_confidence,
        "phone_severity": phone_severity,
        "sensor_source": sensor_source,
        "features": features or {},
        "speed": speed,
        "heading": heading,
        "location_context": {
            "prior_report_count_at_this_location": prior_report_count,
            "prior_unique_device_count_at_this_location": prior_unique_device_count,
        },
        "vision_evidence": vision_evidence or [],
    }

    return (
        SYSTEM_INSTRUCTIONS
        + "\n\nSensor evidence for this event:\n"
        + json.dumps(evidence, indent=2)
    )
