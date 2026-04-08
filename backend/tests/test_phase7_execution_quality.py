from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from tradingbot.db import Base
from tradingbot.enums import (
    BrokerSlug,
    OrderIntent,
    OrderStatus,
    OrderType,
    RiskDecision,
    TimeInForce,
    TradingMode,
)
from tradingbot.models import ExecutionQualitySample, RiskEvent
from tradingbot.schemas.trading import CommitteeDecision, RiskCheckResult
from tradingbot.services.adapters import (
    AccountSnapshot,
    BrokerFill,
    BrokerOrder,
    BrokerPosition,
    LiquiditySnapshot,
    OrderRequest,
    ReplaceOrderRequest,
)
from tradingbot.services.execution import ExecutionService
from tradingbot.services.risk import RiskEngine, RiskPolicy


class QualityAwareAdapter:
    broker_slug = BrokerSlug.ALPACA

    def __init__(self, snapshot: LiquiditySnapshot) -> None:
        self.snapshot = snapshot
        self.place_calls = 0
        self.last_order: OrderRequest | None = None

    def get_account_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(equity=100_000, cash=100_000, buying_power=100_000, daily_pl=0.0)

    def get_account(self) -> AccountSnapshot:
        return self.get_account_snapshot()

    def list_open_orders(self) -> list[BrokerOrder]:
        return []

    def list_positions(self) -> list[BrokerPosition]:
        return []

    def place_order(self, order: OrderRequest) -> BrokerOrder:
        self.place_calls += 1
        self.last_order = order
        return BrokerOrder(
            broker_order_id=f"phase7-broker-{self.place_calls}",
            client_order_id=order.client_order_id or "phase7-client",
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
            raw={"id": f"phase7-broker-{self.place_calls}"},
        )

    def replace_order(self, broker_order_id: str, patch: ReplaceOrderRequest) -> BrokerOrder:
        raise NotImplementedError

    def cancel_order(self, broker_order_id: str) -> bool:
        raise NotImplementedError

    def cancel_all_orders(self) -> int:
        return 0

    def close_all_positions(self) -> int:
        return 0

    def get_order(self, broker_order_id: str) -> BrokerOrder:
        raise NotImplementedError

    def fetch_fills(
        self,
        *,
        since: datetime | None = None,
        limit: int = 200,
        symbol: str | None = None,
    ) -> list[BrokerFill]:
        return []

    def get_liquidity_snapshot(self, symbol: str) -> LiquiditySnapshot | None:
        return self.snapshot if self.snapshot.symbol == symbol else None



def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()



def _approved_decision(symbol: str = "AAPL", *, entry: float = 100.0) -> CommitteeDecision:
    return CommitteeDecision(
        symbol=symbol,
        direction=OrderIntent.BUY,
        confidence=0.84,
        entry=entry,
        stop_loss=entry - 2.0,
        take_profit=entry + 4.0,
        time_horizon="intraday",
        status=RiskDecision.APPROVED,
        thesis="Phase 7 test decision.",
        risk_notes=[],
    )



def test_phase7_rejects_trade_when_expected_fill_quality_is_poor() -> None:
    session = _session()
    adapter = QualityAwareAdapter(
        LiquiditySnapshot(
            symbol="AAPL",
            bid_price=98.0,
            ask_price=102.0,
            bid_size=5,
            ask_size=5,
            last_price=100.0,
            as_of=datetime.now(UTC),
            venue="XNYS",
            raw={},
        )
    )
    service = ExecutionService(session, adapter)

    order = service.submit_trade(
        mode=TradingMode.PAPER,
        decision=_approved_decision("AAPL", entry=100.0),
        risk_result=RiskCheckResult(decision=RiskDecision.APPROVED, approved_quantity=20, notes=[]),
        decision_context={"feature_snapshot": {"intraday_volatility_pct": 3.2, "relative_volume_10": 0.4}},
    )

    risk_event = session.scalar(
        select(RiskEvent)
        .where(RiskEvent.code == "execution_quality_rejected")
        .order_by(RiskEvent.created_at.desc())
    )
    assert order is None
    assert adapter.place_calls == 0
    assert risk_event is not None



def test_phase7_adapts_order_aggressiveness_for_liquid_tight_spread_names() -> None:
    session = _session()
    adapter = QualityAwareAdapter(
        LiquiditySnapshot(
            symbol="MSFT",
            bid_price=409.96,
            ask_price=410.00,
            bid_size=1200,
            ask_size=1300,
            last_price=409.99,
            as_of=datetime.now(UTC),
            venue="XNYS",
            raw={},
        )
    )
    service = ExecutionService(session, adapter)

    order = service.submit_trade(
        mode=TradingMode.PAPER,
        decision=_approved_decision("MSFT", entry=410.0),
        risk_result=RiskCheckResult(decision=RiskDecision.APPROVED, approved_quantity=12, notes=[]),
        decision_context={"feature_snapshot": {"intraday_volatility_pct": 0.9, "relative_volume_10": 1.8}},
    )

    assert order is not None
    assert order.order_type == OrderType.BRACKET
    assert order.time_in_force == TimeInForce.DAY
    assert order.limit_price is None
    assert adapter.last_order is not None
    assert adapter.last_order.time_in_force == TimeInForce.DAY
    assert adapter.last_order.limit_price is None
    assert order.metadata_json["execution_quality"]["aggressiveness"] == "aggressive"



def test_phase7_persists_tca_sample_and_summary_metrics() -> None:
    session = _session()
    adapter = QualityAwareAdapter(
        LiquiditySnapshot(
            symbol="NVDA",
            bid_price=899.5,
            ask_price=900.0,
            bid_size=900,
            ask_size=900,
            last_price=899.8,
            as_of=datetime.now(UTC),
            venue="XNAS",
            raw={},
        )
    )
    service = ExecutionService(session, adapter)

    order = service.submit_trade(
        mode=TradingMode.PAPER,
        decision=_approved_decision("NVDA", entry=900.0),
        risk_result=RiskCheckResult(decision=RiskDecision.APPROVED, approved_quantity=10, notes=[]),
        decision_context={"feature_snapshot": {"intraday_volatility_pct": 1.0, "relative_volume_10": 1.4}},
    )
    assert order is not None

    created = service.ingest_broker_fill(
        BrokerFill(
            broker_fill_id="phase7-fill-1",
            broker_order_id=order.broker_order_id,
            symbol="NVDA",
            side="buy",
            quantity=10,
            price=901.4,
            fee=0.0,
            filled_at=datetime.now(UTC),
            raw={},
        ),
        source="unit",
    )
    session.commit()

    sample = session.scalar(select(ExecutionQualitySample).where(ExecutionQualitySample.order_id == order.id))
    summary = service.execution_quality_summary(dimension="symbol", limit=5)

    assert created is True
    assert sample is not None
    assert sample.outcome_status == OrderStatus.FILLED
    assert sample.realized_slippage_bps is not None
    assert sample.realized_slippage_bps > 0
    assert summary
    assert summary[0]["dimension"] == "symbol"
    assert summary[0]["key"] == "NVDA"



def test_phase7_risk_engine_scales_size_with_execution_feedback() -> None:
    engine = RiskEngine(
        RiskPolicy(
            max_open_positions=10,
            max_daily_loss_pct=0.1,
            max_position_risk_pct=0.01,
            max_symbol_notional_pct=1.5,
            symbol_cooldown_minutes=45,
            max_gross_exposure_pct=2.0,
            max_sector_exposure_pct=2.0,
            max_correlation_exposure_pct=2.0,
            execution_failure_review_threshold=10,
        )
    )

    baseline = engine.validate(
        _approved_decision("TSLA", entry=200.0),
        equity=100_000,
        buying_power=200_000,
        open_positions=1,
        daily_loss_pct=0.0,
        active_symbol_exposure=0.0,
        is_symbol_in_cooldown=False,
        portfolio_exposure=0.0,
        positions=[],
        feature_snapshot={"atr_14": 2.0, "intraday_volatility_pct": 1.0},
        structured_events=[],
    )
    throttled = engine.validate(
        _approved_decision("TSLA", entry=200.0),
        equity=100_000,
        buying_power=200_000,
        open_positions=1,
        daily_loss_pct=0.0,
        active_symbol_exposure=0.0,
        is_symbol_in_cooldown=False,
        portfolio_exposure=0.0,
        positions=[],
        feature_snapshot={"atr_14": 2.0, "intraday_volatility_pct": 1.0},
        structured_events=[],
        execution_quality_feedback={
            "size_scale": 0.55,
            "block_new_entries": False,
            "notes": ["Execution-quality feedback applied size throttling."],
        },
    )

    assert baseline.decision == RiskDecision.APPROVED
    assert throttled.decision == RiskDecision.APPROVED
    assert throttled.approved_quantity < baseline.approved_quantity
