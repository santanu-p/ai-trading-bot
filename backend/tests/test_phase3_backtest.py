from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tradingbot.db import Base
from tradingbot.enums import BrokerSlug, OrderIntent, OrderStatus, OrderType, RiskDecision, TimeInForce, TradingMode
from tradingbot.schemas.settings import TradingProfile
from tradingbot.schemas.trading import CommitteeDecision, RiskCheckResult
from tradingbot.services.adapters import AccountSnapshot, BarPoint, BrokerFill, BrokerOrder, BrokerPosition, NewsItem, OrderRequest
from tradingbot.services.backtest import BacktestService, BacktestSimulationConfig
from tradingbot.services.execution import ExecutionService


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()


def _load_json(name: str) -> list[dict]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


class ReplayMarketDataAdapter:
    def __init__(self, bars: list[BarPoint]) -> None:
        self._bars = bars

    def get_intraday_bars(self, symbol: str, *, start: datetime, end: datetime, interval_minutes: int) -> list[BarPoint]:
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


class FillReplayAdapter:
    broker_slug = BrokerSlug.ALPACA

    def __init__(self) -> None:
        self._order: BrokerOrder | None = None

    def get_account_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(equity=100_000, cash=100_000, buying_power=100_000, daily_pl=0)

    def get_account(self) -> AccountSnapshot:
        return self.get_account_snapshot()

    def list_open_orders(self) -> list[BrokerOrder]:
        if self._order is None:
            return []
        if self._order.status in {OrderStatus.CANCELED, OrderStatus.FILLED}:
            return []
        return [self._order]

    def list_positions(self) -> list[BrokerPosition]:
        return []

    def place_order(self, order: OrderRequest) -> BrokerOrder:
        self._order = BrokerOrder(
            broker_order_id="fixture-order-1",
            client_order_id=order.client_order_id or "fixture",
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            time_in_force=order.time_in_force,
            quantity=order.quantity,
            filled_quantity=0,
            average_fill_price=None,
            limit_price=order.limit_price,
            stop_price=order.stop_price,
            take_profit=order.take_profit,
            trailing_percent=order.trailing_percent,
            trailing_amount=order.trailing_amount,
            status=OrderStatus.ACCEPTED,
            status_reason=None,
            updated_at=datetime.now(UTC),
            raw={},
        )
        return self._order

    def replace_order(self, broker_order_id: str, patch):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def cancel_order(self, broker_order_id: str) -> bool:
        del broker_order_id
        return True

    def cancel_all_orders(self) -> int:
        return 0

    def close_all_positions(self) -> int:
        return 0

    def get_order(self, broker_order_id: str) -> BrokerOrder:
        if self._order is None or self._order.broker_order_id != broker_order_id:
            raise ValueError("order not found")
        return self._order

    def fetch_fills(self, *, since=None, limit: int = 200, symbol: str | None = None):  # type: ignore[no-untyped-def]
        del since, limit, symbol
        return []


def _bars() -> list[BarPoint]:
    rows = _load_json("backtest_bars_aapl.json")
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


def _news() -> list[NewsItem]:
    rows = _load_json("backtest_news_aapl.json")
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


def test_phase3_backtest_replay_is_deterministic() -> None:
    service = BacktestService(ReplayMarketDataAdapter(_bars()), ReplayNewsAdapter(_news()))
    config = BacktestSimulationConfig(
        initial_equity=100_000,
        slippage_bps=5,
        commission_per_share=0.005,
        fill_delay_bars=1,
        reject_probability=0.03,
        max_holding_bars=16,
        random_seed=17,
    )
    profile = TradingProfile()
    start = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
    end = datetime(2026, 1, 5, 16, 55, tzinfo=UTC)

    result_a = service.run_research(
        symbols=["AAPL"],
        start=start,
        end=end,
        interval_minutes=5,
        trading_profile=profile,
        config=config,
    )
    result_b = service.run_research(
        symbols=["AAPL"],
        start=start,
        end=end,
        interval_minutes=5,
        trading_profile=profile,
        config=config,
    )

    assert result_a.metrics == result_b.metrics
    assert result_a.walk_forward == result_b.walk_forward
    assert result_a.regime_breakdown == result_b.regime_breakdown
    assert [trade.to_payload() for trade in result_a.trades] == [trade.to_payload() for trade in result_b.trades]


def test_phase3_backtest_matches_expected_snapshot() -> None:
    expected = json.loads((FIXTURE_DIR / "backtest_expected_snapshot.json").read_text(encoding="utf-8"))
    service = BacktestService(ReplayMarketDataAdapter(_bars()), ReplayNewsAdapter(_news()))
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
        symbols=["AAPL"],
        start=datetime(2026, 1, 5, 14, 30, tzinfo=UTC),
        end=datetime(2026, 1, 5, 16, 55, tzinfo=UTC),
        interval_minutes=5,
        trading_profile=TradingProfile(),
        config=config,
    )
    first_trade = result.trades[0] if result.trades else None

    assert result.metrics == expected["metrics"]
    assert len(result.trades) == expected["trade_count"]
    assert len([item for item in result.trades if item.status == "rejected"]) == expected["rejected_orders"]
    assert result.regime_breakdown == expected["regime_breakdown"]
    assert result.walk_forward == expected["walk_forward"]
    assert first_trade is not None
    assert first_trade.to_payload() == expected["first_trade"]


def test_phase3_broker_fill_fixture_drives_order_to_filled() -> None:
    session = _session()
    execution = ExecutionService(session, FillReplayAdapter())
    order = execution.submit_trade(
        mode=TradingMode.PAPER,
        decision=CommitteeDecision(
            symbol="AAPL",
            direction=OrderIntent.BUY,
            confidence=0.75,
            entry=155.4,
            stop_loss=154.6,
            take_profit=156.8,
            time_horizon="intraday",
            status=RiskDecision.APPROVED,
            thesis="Fixture-backed entry",
            risk_notes=[],
        ),
        risk_result=RiskCheckResult(decision=RiskDecision.APPROVED, approved_quantity=10, notes=[]),
    )
    assert order is not None
    assert order.broker_order_id == "fixture-order-1"

    for row in _load_json("replay_broker_fills.json"):
        fill = BrokerFill(
            broker_fill_id=row["broker_fill_id"],
            broker_order_id=row["broker_order_id"],
            symbol=row["symbol"],
            side=row["side"],
            quantity=int(row["quantity"]),
            price=float(row["price"]),
            fee=float(row["fee"]),
            filled_at=datetime.fromisoformat(row["filled_at"].replace("Z", "+00:00")),
            raw=row,
        )
        execution.ingest_broker_fill(fill, source="fixture")
        session.commit()

    refreshed = session.get(type(order), order.id)
    assert refreshed is not None
    assert refreshed.status == OrderStatus.FILLED
    assert refreshed.filled_quantity == 10
