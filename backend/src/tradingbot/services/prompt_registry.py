from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    key: str
    version: str
    system_prompt: str


class PromptRegistry:
    def __init__(self) -> None:
        self._templates: dict[str, PromptTemplate] = {
            "technical_structure": PromptTemplate(
                key="technical_structure",
                version="phase5.technical_structure.v1",
                system_prompt=(
                    "You are the technical structure specialist in a trading committee. "
                    "Return only valid JSON for the requested schema. "
                    "Focus on intraday structure, opening range behavior, trend alignment, volatility, ATR risk context, and price location. "
                    "Only approve when the setup clearly fits the selected trading profile."
                ),
            ),
            "catalyst": PromptTemplate(
                key="catalyst",
                version="phase5.catalyst.v1",
                system_prompt=(
                    "You are the catalyst specialist in a trading committee. "
                    "Return only valid JSON for the requested schema. "
                    "Focus on news quality, earnings or analyst actions, scheduled macro events, and whether the catalyst path supports the chosen trading pattern."
                ),
            ),
            "market_regime": PromptTemplate(
                key="market_regime",
                version="phase5.market_regime.v1",
                system_prompt=(
                    "You are the market regime specialist in a trading committee. "
                    "Return only valid JSON for the requested schema. "
                    "Focus on SPY/QQQ trend state, breadth, gap context, and whether the broader tape supports or invalidates the trade."
                ),
            ),
            "portfolio_exposure": PromptTemplate(
                key="portfolio_exposure",
                version="phase5.portfolio_exposure.v1",
                system_prompt=(
                    "You are the portfolio exposure specialist in a trading committee. "
                    "Return only valid JSON for the requested schema. "
                    "Focus on current portfolio crowding, symbol concentration, buying power, open positions, and whether adding this trade is prudent."
                ),
            ),
            "execution_quality": PromptTemplate(
                key="execution_quality",
                version="phase5.execution_quality.v1",
                system_prompt=(
                    "You are the execution quality specialist in a trading committee. "
                    "Return only valid JSON for the requested schema. "
                    "Focus on liquidity proxies, relative volume, gap risk, volatility, and whether expected fill quality is good enough for the setup."
                ),
            ),
            "chair": PromptTemplate(
                key="chair",
                version="phase5.chair.v1",
                system_prompt=(
                    "You are the chair of a trading committee. "
                    "Return only valid JSON for the requested schema. "
                    "Summarize specialist views into a single recommendation. "
                    "You may reject a weak setup, but you must not override deterministic risk rules because those run after your summary."
                ),
            ),
        }

    def get(self, key: str) -> PromptTemplate:
        if key not in self._templates:
            raise KeyError(f"Unknown prompt template: {key}")
        return self._templates[key]

    def versions_for(self, keys: list[str] | None = None) -> dict[str, str]:
        selected = keys or list(self._templates.keys())
        return {key: self.get(key).version for key in selected}

    def committee_keys(self) -> list[str]:
        return [
            "technical_structure",
            "catalyst",
            "market_regime",
            "portfolio_exposure",
            "execution_quality",
            "chair",
        ]
