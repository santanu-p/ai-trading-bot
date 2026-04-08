from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from tradingbot.config import get_settings

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None

try:
    from google import genai
except Exception:  # pragma: no cover - optional dependency
    genai = None


class LLMClient(ABC):
    @abstractmethod
    def complete_json(self, *, system_prompt: str, prompt_payload: dict[str, Any]) -> str:
        raise NotImplementedError


class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str) -> None:
        if OpenAI is None:
            raise RuntimeError("openai is not installed. Install it to use OPENAI_API_KEY.")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def complete_json(self, *, system_prompt: str, prompt_payload: dict[str, Any]) -> str:
        response = self.client.responses.create(
            model=self.model,
            instructions=system_prompt,
            input=json.dumps(prompt_payload, indent=2),
        )
        return response.output_text


class GeminiClient(LLMClient):
    def __init__(self, api_key: str, model: str) -> None:
        if genai is None:
            raise RuntimeError("google-genai is not installed. Install it to use GEMINI_API_KEY.")
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def complete_json(self, *, system_prompt: str, prompt_payload: dict[str, Any]) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            contents=json.dumps(prompt_payload, indent=2),
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
            },
        )
        return response.text or ""


def build_llm_client(model: str | None = None) -> LLMClient:
    settings = get_settings()
    if settings.openai_api_key:
        return OpenAIClient(settings.openai_api_key, model or settings.openai_model)
    if settings.gemini_api_key:
        return GeminiClient(settings.gemini_api_key, model or settings.gemini_model)
    raise RuntimeError("Set OPENAI_API_KEY or GEMINI_API_KEY to run the agent layer.")
