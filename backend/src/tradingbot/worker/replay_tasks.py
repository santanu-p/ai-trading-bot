from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from celery.result import AsyncResult

from tradingbot.schemas.settings import TradingProfile
from tradingbot.services.adapters import BarPoint, NewsItem
from tradingbot.services.backtest import BacktestService, BacktestSimulationConfig
from tradingbot.worker.celery_app import celery_app

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


class ReplayMarketDataAdapter:
    def __init__(self, bars: list[BarPoint]) -> None:
        self._bars = bars

    def get_intraday_bars(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
        interval_minutes: int,
    ) -> list[BarPoint]:
        del symbol, interval_minutes
        return [row for row in self._bars if start <= row.timestamp <= end]


class ReplayNewsAdapter:
    def __init__(self, news_items: list[NewsItem]) -> None:
        self._news_items = news_items

    def get_recent_news(self, symbol: str, *, limit: int = 10) -> list[NewsItem]:
        del symbol
        return sorted(self._news_items, key=lambda item: item.created_at, reverse=True)[:limit]

    def get_news_between(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
        limit: int = 200,
    ) -> list[NewsItem]:
        del symbol
        rows = [item for item in self._news_items if start <= item.created_at <= end]
        return sorted(rows, key=lambda item: item.created_at)[:limit]


def enqueue_replay_regression(symbol: str = "AAPL") -> AsyncResult:
    return run_replay_regression.delay(symbol)


@celery_app.task(name="tradingbot.worker.replay_tasks.run_replay_regression")
def run_replay_regression(symbol: str = "AAPL") -> dict[str, object]:
    normalized_symbol = symbol.upper().strip() or "AAPL"
    snapshot = _build_snapshot(normalized_symbol)
    expected_snapshot = _expected_snapshot(normalized_symbol)
    return {
        "symbol": normalized_symbol,
        "matches_expected": expected_snapshot is not None and snapshot == expected_snapshot,
        "digest": _payload_digest(snapshot),
        "snapshot": snapshot,
    }


def _build_snapshot(symbol: str) -> dict[str, object]:
    bars = _bars(symbol)
    news = _news(symbol)
    service = BacktestService(ReplayMarketDataAdapter(bars), ReplayNewsAdapter(news))
    config = BacktestSimulationConfig(
        initial_equity=100_000,
        slippage_bps=5,
        commission_per_share=0.005,
        fill_delay_bars=1,
        reject_probability=0.03,
        max_holding_bars=16,
        random_seed=17,
    )
    result = service.run_research(
        symbols=[symbol],
        start=datetime(2026, 1, 5, 14, 30, tzinfo=UTC),
        end=datetime(2026, 1, 5, 16, 55, tzinfo=UTC),
        interval_minutes=5,
        trading_profile=TradingProfile(),
        config=config,
    )
    first_trade = result.trades[0] if result.trades else None
    return {
        "metrics": result.metrics,
        "trade_count": len(result.trades),
        "rejected_orders": len([item for item in result.trades if item.status == "rejected"]),
        "regime_breakdown": result.regime_breakdown,
        "walk_forward": result.walk_forward,
        "first_trade": first_trade.to_payload() if first_trade is not None else None,
    }


def _bars(symbol: str) -> list[BarPoint]:
    rows = _fixture_rows(f"backtest_bars_{symbol.lower()}.json")
    return [
        BarPoint(
            timestamp=datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")),
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            volume=float(item["volume"]),
        )
        for item in rows
    ]


def _news(symbol: str) -> list[NewsItem]:
    rows = _fixture_rows(f"backtest_news_{symbol.lower()}.json")
    return [
        NewsItem(
            headline=item["headline"],
            summary=item["summary"],
            source=item["source"],
            created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
            sentiment_hint=item["sentiment_hint"],
        )
        for item in rows
    ]


def _expected_snapshot(symbol: str) -> dict[str, object] | None:
    if symbol != "AAPL":
        return None
    return _fixture_rows("backtest_expected_snapshot.json")


def _fixture_rows(name: str) -> dict[str, object] | list[dict[str, object]]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _payload_digest(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
