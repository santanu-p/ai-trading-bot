from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from tradingbot.config import get_settings
from tradingbot.enums import AgentRole
from tradingbot.schemas.settings import TradingProfile
from tradingbot.schemas.trading import AgentDecision
from tradingbot.services.adapters import NewsItem


class OpenAIAgentRunner:
    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY must be configured.")
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = model or settings.openai_model

    def _run_json_prompt(self, system_prompt: str, prompt_payload: dict[str, Any]) -> AgentDecision:
        prompt = json.dumps(prompt_payload, indent=2)
        response = self.client.responses.create(
            model=self.model,
            instructions=system_prompt,
            input=prompt,
        )
        return AgentDecision.model_validate_json(response.output_text)

    def market_agent(self, symbol: str, indicators: dict[str, float], trading_profile: TradingProfile) -> AgentDecision:
        system_prompt = (
            "You are the market agent in a trading committee. "
            "Return valid JSON that matches the required schema. "
            "First align your analysis to the user's selected trading pattern, instrument class, strategy family, risk profile, and market universe. "
            "If the setup does not match the selected trading pattern, return hold and explain why."
        )
        payload = {
            "role": AgentRole.MARKET.value,
            "symbol": symbol,
            "indicators": indicators,
            "trading_profile": trading_profile.model_dump(mode="json"),
        }
        return self._run_json_prompt(system_prompt, payload)

    def news_agent(self, symbol: str, news_items: list[NewsItem], trading_profile: TradingProfile) -> AgentDecision:
        system_prompt = (
            "You are the news agent in a trading committee. "
            "Return valid JSON that matches the required schema. "
            "First align your analysis to the user's selected trading pattern, instrument class, strategy family, risk profile, and market universe. "
            "Use hold when the catalyst picture does not fit the chosen pattern or the signal is weak."
        )
        payload = {
            "role": AgentRole.NEWS.value,
            "symbol": symbol,
            "trading_profile": trading_profile.model_dump(mode="json"),
            "news": [
                {
                    "headline": item.headline,
                    "summary": item.summary,
                    "source": item.source,
                    "created_at": item.created_at.isoformat(),
                }
                for item in news_items
            ],
        }
        return self._run_json_prompt(system_prompt, payload)
