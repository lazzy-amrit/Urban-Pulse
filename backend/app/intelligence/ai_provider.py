"""
Gemini client: native SDK, structured output, bounded concurrency.

A 429 or malformed response raises immediately — no in-request retries,
no fallback-model chaining. The caller (classifier.py) catches and uses
the local rule-based fallback. This keeps one bad Gemini response from
turning into a burst of extra requests.
"""

import asyncio
import logging

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, field_validator

from app.core.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT_SECONDS, GEMINI_MAX_CONCURRENT_REQUESTS

logger = logging.getLogger("urban_pulse.intelligence")

ALLOWED_CLASSIFICATIONS = {
    "road_anomaly",
    "surface_irregularity",
    "impact_event",
    "pothole_likely",
    "speed_bump_likely",
    "unknown",
}


class AIInterpretation(BaseModel):
    classification: str
    confidence: float = Field(ge=0.0, le=1.0)
    severity: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str = ""

    @field_validator("classification")
    @classmethod
    def known_classification(cls, v: str) -> str:
        return v if v in ALLOWED_CLASSIFICATIONS else "unknown"


class RateLimited(Exception):
    pass


_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "classification": {"type": "STRING", "enum": sorted(ALLOWED_CLASSIFICATIONS)},
        "confidence": {"type": "NUMBER"},
        "severity": {"type": "NUMBER"},
        "reasoning_summary": {"type": "STRING"},
    },
    "required": ["classification", "confidence", "severity"],
}

_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
_semaphore = asyncio.Semaphore(GEMINI_MAX_CONCURRENT_REQUESTS)


def is_configured() -> bool:
    return _client is not None


async def analyze_sensor_event(prompt: str) -> AIInterpretation:
    if _client is None:
        raise RuntimeError("Gemini is not configured")

    async with _semaphore:
        try:
            response = await asyncio.wait_for(
                _client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        max_output_tokens=300,
                        response_mime_type="application/json",
                        response_schema=_RESPONSE_SCHEMA,
                    ),
                ),
                timeout=GEMINI_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise
        except Exception as exc:
            if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                raise RateLimited() from exc
            raise

    if not response.text:
        raise ValueError("Gemini returned an empty response")

    return AIInterpretation.model_validate_json(response.text)
