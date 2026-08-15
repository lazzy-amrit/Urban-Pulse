"""
AI provider abstraction.

`AIProvider` defines the interface the rest of the app depends on. Concrete
providers (e.g. Anthropic) implement it. The provider is selected at runtime
based on AI_PROVIDER / AI_API_KEY / AI_MODEL — nothing else in the codebase
should hardcode a specific vendor.

If no provider is configured, `get_ai_provider()` returns None and callers
must use app/intelligence/fallback.py instead.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

import httpx
from pydantic import BaseModel, Field, field_validator

from app.core.config import (
    AI_PROVIDER,
    AI_API_KEY,
    AI_MODEL,
    AI_MODEL_FALLBACK,
    AI_REQUEST_TIMEOUT_SECONDS,
)

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
    """Structured, validated output of the AI interpretation step."""

    classification: str = Field(...)
    confidence: float = Field(..., ge=0.0, le=1.0)
    severity: float = Field(..., ge=0.0, le=1.0)
    reasoning_summary: str = ""

    @field_validator("classification")
    @classmethod
    def classification_must_be_known(cls, v: str) -> str:
        if v not in ALLOWED_CLASSIFICATIONS:
            return "unknown"
        return v


class AIProvider(ABC):
    @abstractmethod
    def analyze_sensor_event(self, prompt: str) -> AIInterpretation:
        """
        Send the prompt to the AI backend and return a validated
        AIInterpretation. Implementations should raise on failure
        (timeout, malformed response, HTTP error) — the caller
        (classifier.py) is responsible for catching and falling back.
        """
        raise NotImplementedError


class AnthropicProvider(AIProvider):
    """Minimal Anthropic Messages API client, used when AI_PROVIDER=anthropic."""

    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._model = model

    def analyze_sensor_event(self, prompt: str) -> AIInterpretation:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self._model,
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=AI_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        text_blocks = [
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        ]
        raw_text = "".join(text_blocks).strip()
        raw_text = raw_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        parsed = json.loads(raw_text)
        return AIInterpretation(**parsed)


class GeminiProvider(AIProvider):
    """
    Google AI Studio (Gemini) client, used when AI_PROVIDER=gemini.

    Tries a list of models in order — by default gemini-2.5-flash first,
    then gemini-2.5-flash-lite. Flash gives better quality but a much
    lower free-tier daily quota (~100 RPD); Flash-Lite has a smaller
    quality edge but a far higher quota (~1000 RPD). Falling through to
    Flash-Lite when Flash is rate-limited means the AI path only drops
    to the fully local rule-based fallback once BOTH quotas are spent.

    Uses Gemini's native structured-output support (responseSchema) so
    the model is constrained to the exact fields we need.
    """

    def __init__(self, api_key: str, models: list[str]):
        self._api_key = api_key
        self._models = models

    def analyze_sensor_event(self, prompt: str) -> AIInterpretation:
        last_error: Exception | None = None

        for model in self._models:
            try:
                return self._call_model(model, prompt)
            except Exception as exc:  # noqa: BLE001 — try next model on any failure
                last_error = exc
                logger.warning("Gemini model '%s' failed, trying next: %s", model, exc)

        # Every model in the chain failed — let the caller (classifier.py)
        # fall back to the fully local rule-based interpretation.
        raise last_error or RuntimeError("All configured Gemini models failed")

    def _call_model(self, model: str, prompt: str) -> AIInterpretation:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        response = httpx.post(
            url,
            params={"key": self._api_key},
            headers={"content-type": "application/json"},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 300,
                    "responseMimeType": "application/json",
                    "responseSchema": {
                        "type": "OBJECT",
                        "properties": {
                            "classification": {
                                "type": "STRING",
                                "enum": sorted(ALLOWED_CLASSIFICATIONS),
                            },
                            "confidence": {"type": "NUMBER"},
                            "severity": {"type": "NUMBER"},
                            "reasoning_summary": {"type": "STRING"},
                        },
                        "required": ["classification", "confidence", "severity"],
                    },
                },
            },
            timeout=AI_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError(f"Gemini model '{model}' response had no candidates")

        parts = candidates[0].get("content", {}).get("parts", [])
        raw_text = "".join(part.get("text", "") for part in parts).strip()
        raw_text = raw_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        parsed = json.loads(raw_text)
        return AIInterpretation(**parsed)


def get_ai_provider() -> Optional[AIProvider]:
    """
    Returns a configured AIProvider, or None if no provider is configured.
    Add additional `elif` branches here to support more providers without
    touching any other file.
    """
    if not AI_PROVIDER or not AI_API_KEY:
        return None

    provider_name = AI_PROVIDER.strip().lower()

    if provider_name == "anthropic":
        model = AI_MODEL or "claude-sonnet-4-6"
        return AnthropicProvider(api_key=AI_API_KEY, model=model)

    if provider_name == "gemini":
        # Primary: AI_MODEL (default gemini-2.5-flash, better quality).
        # Fallback: AI_MODEL_FALLBACK (default gemini-2.5-flash-lite, much
        # higher free-tier daily quota) — tried only if the primary fails.
        primary = AI_MODEL or "gemini-2.5-flash"
        fallback = AI_MODEL_FALLBACK or "gemini-2.5-flash-lite"
        models = [primary] if primary == fallback else [primary, fallback]
        return GeminiProvider(api_key=AI_API_KEY, models=models)

    logger.warning("unsupported AI_PROVIDER configured: %s", provider_name)
    return None