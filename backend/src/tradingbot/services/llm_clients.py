from __future__ import annotations

import json
from abc import ABC, abstractmethod
from time import perf_counter, sleep
from typing import Any

from tradingbot.config import get_settings
from tradingbot.services.metrics import observe_counter, observe_duration_ms

OpenAIClientImpl: Any | None
try:
    from openai import OpenAI as OpenAIClientImpl
except Exception:  # pragma: no cover - optional dependency
    OpenAIClientImpl = None

_genai_module: Any | None
try:
    from google import genai as _genai_module
except Exception:  # pragma: no cover - optional dependency
    _genai_module = None

# Retry configuration
_MAX_RETRIES = 3
_RETRY_BASE_DELAY_SECONDS = 1.0
_RETRY_BACKOFF_MULTIPLIER = 2.0
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _is_retryable(exc: Exception) -> bool:
    """Determine if an LLM exception is transient and worth retrying."""
    exc_str = str(exc).lower()
    # Check for common transient error patterns
    if any(keyword in exc_str for keyword in ("rate limit", "timeout", "overloaded", "capacity", "unavailable")):
        return True
    # Check for HTTP status codes embedded in exception
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if isinstance(status_code, int) and status_code in _RETRYABLE_STATUS_CODES:
        return True
    return False


class LLMClient(ABC):
    @abstractmethod
    def complete_json(self, *, system_prompt: str, prompt_payload: dict[str, Any]) -> str:
        raise NotImplementedError


class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str) -> None:
        if OpenAIClientImpl is None:
            raise RuntimeError("openai is not installed. Install it to use OPENAI_API_KEY.")
        self.client = OpenAIClientImpl(api_key=api_key)
        self.model = model

    def complete_json(self, *, system_prompt: str, prompt_payload: dict[str, Any]) -> str:
        started = perf_counter()
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = self.client.responses.create(
                    model=self.model,
                    instructions=system_prompt,
                    input=json.dumps(prompt_payload, indent=2),
                )
                observe_counter("external.llm.requests", tags={"provider": "openai", "status": "success"})
                return response.output_text
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1 and _is_retryable(exc):
                    delay = _RETRY_BASE_DELAY_SECONDS * (_RETRY_BACKOFF_MULTIPLIER ** attempt)
                    observe_counter(
                        "external.llm.retries",
                        tags={"provider": "openai", "attempt": str(attempt + 1)},
                    )
                    sleep(delay)
                    continue
                observe_counter("external.llm.requests", tags={"provider": "openai", "status": "error"})
                raise
            finally:
                if attempt == _MAX_RETRIES - 1 or not (last_exc and _is_retryable(last_exc)):
                    observe_duration_ms(
                        "external.llm.latency_ms",
                        duration_ms=(perf_counter() - started) * 1000,
                        tags={"provider": "openai", "model": self.model},
                    )
        # Should not reach here, but satisfy type checker
        observe_counter("external.llm.requests", tags={"provider": "openai", "status": "error"})
        raise last_exc  # type: ignore[misc]


class GeminiClient(LLMClient):
    def __init__(self, api_key: str, model: str) -> None:
        if _genai_module is None:
            raise RuntimeError("google-genai is not installed. Install it to use GEMINI_API_KEY.")
        self.client = _genai_module.Client(api_key=api_key)
        self.model = model

    def complete_json(self, *, system_prompt: str, prompt_payload: dict[str, Any]) -> str:
        started = perf_counter()
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=json.dumps(prompt_payload, indent=2),
                    config={
                        "system_instruction": system_prompt,
                        "response_mime_type": "application/json",
                    },
                )
                observe_counter("external.llm.requests", tags={"provider": "gemini", "status": "success"})
                return response.text or ""
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1 and _is_retryable(exc):
                    delay = _RETRY_BASE_DELAY_SECONDS * (_RETRY_BACKOFF_MULTIPLIER ** attempt)
                    observe_counter(
                        "external.llm.retries",
                        tags={"provider": "gemini", "attempt": str(attempt + 1)},
                    )
                    sleep(delay)
                    continue
                observe_counter("external.llm.requests", tags={"provider": "gemini", "status": "error"})
                raise
            finally:
                if attempt == _MAX_RETRIES - 1 or not (last_exc and _is_retryable(last_exc)):
                    observe_duration_ms(
                        "external.llm.latency_ms",
                        duration_ms=(perf_counter() - started) * 1000,
                        tags={"provider": "gemini", "model": self.model},
                    )
        # Should not reach here, but satisfy type checker
        observe_counter("external.llm.requests", tags={"provider": "gemini", "status": "error"})
        raise last_exc  # type: ignore[misc]


def build_llm_client(model: str | None = None) -> LLMClient:
    settings = get_settings()
    if settings.openai_api_key:
        return OpenAIClient(settings.openai_api_key, model or settings.openai_model)
    if settings.gemini_api_key:
        return GeminiClient(settings.gemini_api_key, model or settings.gemini_model)
    raise RuntimeError("Set OPENAI_API_KEY or GEMINI_API_KEY to run the agent layer.")
