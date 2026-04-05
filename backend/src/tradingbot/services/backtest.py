from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from tradingbot.schemas.settings import TradingProfile
from tradingbot.services.adapters import MarketDataAdapter, NewsAdapter
from tradingbot.services.agents import OpenAIAgentRunner
from tradingbot.services.committee import CommitteeService
from tradingbot.services.indicators import bar_summary
from tradingbot.services.risk import RiskEngine


@dataclass(slots=True)
class BacktestSlice:
    symbol: str
    timestamp: datetime
    decision_status: str
    confidence: float


class BacktestService:
    def __init__(
        self,
        market_data: MarketDataAdapter,
        news_data: NewsAdapter,
        agent_runner: OpenAIAgentRunner,
        committee_service: CommitteeService,
        risk_engine: RiskEngine,
    ) -> None:
        self.market_data = market_data
        self.news_data = news_data
        self.agent_runner = agent_runner
        self.committee_service = committee_service
        self.risk_engine = risk_engine

    def replay_symbol(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval_minutes: int,
        trading_profile: TradingProfile,
    ) -> list[BacktestSlice]:
        cursor = start
        results: list[BacktestSlice] = []
        while cursor < end:
            window_end = cursor + timedelta(minutes=interval_minutes * 40)
            bars = self.market_data.get_intraday_bars(symbol, start=cursor, end=window_end, interval_minutes=interval_minutes)
            indicators = bar_summary(bars)
            news = self.news_data.get_recent_news(symbol, limit=8)
            market_decision = self.agent_runner.market_agent(symbol, indicators, trading_profile)
            news_decision = self.agent_runner.news_agent(symbol, news, trading_profile)
            proposal = self.committee_service.propose(market_decision, news_decision)
            risk_result = self.risk_engine.validate(
                proposal,
                equity=100_000,
                buying_power=100_000,
                open_positions=0,
                daily_loss_pct=0,
                active_symbol_exposure=0,
                is_symbol_in_cooldown=False,
            )
            final_decision = self.committee_service.finalize(proposal, risk_result=risk_result)
            results.append(
                BacktestSlice(
                    symbol=symbol,
                    timestamp=window_end,
                    decision_status=final_decision.status.value,
                    confidence=final_decision.confidence,
                )
            )
            cursor = window_end
        return results
