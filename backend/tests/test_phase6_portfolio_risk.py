from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from tradingbot.db import Base
from tradingbot.enums import (
    BrokerSlug,
    ExecutionIntentStatus,
    ExecutionIntentType,
    OrderIntent,
    OrderStatus,
    OrderType,
    RiskDecision,
    RunStatus,
    TradingMode,
)
from tradingbot.models import AgentRun, BotSettings, ExecutionIntent, OrderRecord, RiskEvent, SymbolCooldown
from tradingbot.schemas.trading import CommitteeDecision, RiskCheckResult
from tradingbot.services.adapters import AccountSnapshot, BrokerFill, BrokerPosition
from tradingbot.services.execution import ExecutionService
from tradingbot.services.risk import PortfolioRiskService, PositionExposure, RiskEngine, RiskPolicy, risk_policy_from_settings


class StubExecutionAdapter:
    broker_slug = BrokerSlug.ALPACA

    def get_account_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(equity=100_000, cash=100_000, buying_power=100_000, daily_pl=0.0)

    def get_account(self) -> AccountSnapshot:
        return self.get_account_snapshot()

    def list_open_orders(self) -> list:
        return []

    def list_positions(self) -> list[BrokerPosition]:
        return []

    def place_order(self, order):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def replace_order(self, broker_order_id: str, patch):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def cancel_order(self, broker_order_id: str) -> bool:
        raise NotImplementedError

    def cancel_all_orders(self) -> int:
        return 0

    def close_all_positions(self) -> int:
        return 0

    def get_order(self, broker_order_id: str):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def fetch_fills(self, *, since=None, limit: int = 200, symbol: str | None = None):  # type: ignore[no-untyped-def]
        return []


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()


def _approved_decision(symbol: str = "AAPL", confidence: float = 0.8) -> CommitteeDecision:
    return CommitteeDecision(
        symbol=symbol,
        direction=OrderIntent.BUY,
        confidence=confidence,
        entry=100.0,
        stop_loss=96.0,
        take_profit=108.0,
        time_horizon="intraday",
        status=RiskDecision.APPROVED,
        thesis="Structured committee approved long setup.",
        risk_notes=[],
    )


def test_phase6_rejects_sector_and_correlation_concentration() -> None:
    engine = RiskEngine(
        RiskPolicy(
            max_open_positions=10,
            max_daily_loss_pct=0.05,
            max_position_risk_pct=0.01,
            max_symbol_notional_pct=0.5,
            symbol_cooldown_minutes=45,
            max_gross_exposure_pct=0.9,
            max_sector_exposure_pct=0.3,
            max_correlation_exposure_pct=0.35,
            intraday_drawdown_pause_pct=0.2,
            execution_failure_review_threshold=10,
        )
    )

    result = engine.validate(
        _approved_decision("AAPL"),
        equity=100_000,
        buying_power=100_000,
        open_positions=2,
        daily_loss_pct=0.0,
        active_symbol_exposure=0.0,
        is_symbol_in_cooldown=False,
        portfolio_exposure=40_000,
        positions=[PositionExposure(symbol="MSFT", market_value=40_000, side="long")],
        feature_snapshot={"atr_14": 1.8, "intraday_volatility_pct": 1.0},
        structured_events=[{"event_type": "sector_etf_context", "payload": {"sector_etf": "XLK"}}],
    )

    assert result.decision == RiskDecision.REJECTED
    assert any("Sector exposure cap breached" in note for note in result.notes)
    assert any("Correlation exposure cap breached" in note for note in result.notes)


def test_phase6_dynamic_sizing_throttles_after_drawdown_and_loss_streak() -> None:
    policy = RiskPolicy(
        max_open_positions=10,
        max_daily_loss_pct=0.1,
        max_position_risk_pct=0.01,
        max_symbol_notional_pct=0.8,
        symbol_cooldown_minutes=45,
        max_gross_exposure_pct=1.2,
        max_sector_exposure_pct=1.0,
        max_correlation_exposure_pct=1.0,
        volatility_target_pct=1.5,
        intraday_drawdown_pause_pct=0.2,
        loss_streak_reduction_threshold=2,
        loss_streak_size_scale=0.5,
        equity_curve_throttle_start_pct=0.01,
        equity_curve_throttle_min_scale=0.35,
        execution_failure_review_threshold=10,
    )
    engine = RiskEngine(policy)
    decision = _approved_decision("JPM", confidence=0.92)

    baseline = engine.validate(
        decision,
        equity=100_000,
        buying_power=100_000,
        open_positions=1,
        daily_loss_pct=0.0,
        active_symbol_exposure=0.0,
        is_symbol_in_cooldown=False,
        portfolio_exposure=0.0,
        positions=[],
        feature_snapshot={"atr_14": 1.2, "intraday_volatility_pct": 1.0},
        structured_events=[],
        equity_drawdown_pct=0.0,
        loss_streak=0,
        recent_execution_failures=0,
    )
    throttled = engine.validate(
        decision,
        equity=100_000,
        buying_power=100_000,
        open_positions=1,
        daily_loss_pct=0.0,
        active_symbol_exposure=0.0,
        is_symbol_in_cooldown=False,
        portfolio_exposure=0.0,
        positions=[],
        feature_snapshot={"atr_14": 1.2, "intraday_volatility_pct": 2.8},
        structured_events=[],
        equity_drawdown_pct=0.06,
        loss_streak=3,
        recent_execution_failures=0,
    )

    assert baseline.decision == RiskDecision.APPROVED
    assert throttled.decision == RiskDecision.APPROVED
    assert throttled.approved_quantity < baseline.approved_quantity


def test_phase6_auto_kill_switch_triggers_on_severe_anomaly_cluster() -> None:
    session = _session()
    settings = BotSettings(id=1, severe_anomaly_kill_switch_threshold=2, kill_switch_enabled=False)
    session.add(settings)
    now = datetime.now(UTC)
    session.add_all(
        [
            RiskEvent(symbol=None, severity="critical", code="scan_failure", message="failure 1", payload={}),
            RiskEvent(symbol=None, severity="critical", code="broker_submit_failed", message="failure 2", payload={}),
        ]
    )
    session.commit()

    service = PortfolioRiskService(session, risk_policy_from_settings(settings))
    runtime = service.compute_runtime_metrics(equity=100_000, positions=[], now=now)
    triggered = service.trigger_kill_switch_if_needed(settings, runtime=runtime)
    session.commit()

    assert triggered is True
    assert settings.kill_switch_enabled is True
    assert settings.live_enabled is False


def test_phase6_exit_fill_creates_contextual_symbol_cooldown() -> None:
    session = _session()
    session.add(BotSettings(id=1, symbol_cooldown_event_minutes=180, symbol_cooldown_whipsaw_minutes=120))
    run = AgentRun(
        symbol="AAPL",
        status=RunStatus.SUCCEEDED,
        model_name="gpt-5-mini",
        prompt_versions_json={"chair": "phase5.chair.v1"},
    )
    session.add(run)
    session.flush()

    intent = ExecutionIntent(
        source_run_id=run.id,
        intent_type=ExecutionIntentType.TRADE,
        mode=TradingMode.PAPER,
        status=ExecutionIntentStatus.EXECUTED,
        symbol="AAPL",
        direction=OrderIntent.BUY,
        quantity=10,
        limit_price=100.0,
        stop_loss=98.0,
        take_profit=104.0,
        requires_human_approval=False,
        idempotency_key="phase6-cooldown-intent",
        decision_payload={"symbol": "AAPL"},
        risk_payload=RiskCheckResult(decision=RiskDecision.APPROVED, approved_quantity=10, notes=[]).model_dump(mode="json"),
        metadata_json={},
    )
    session.add(intent)
    session.flush()

    parent = OrderRecord(
        execution_intent_id=intent.id,
        symbol="AAPL",
        mode=TradingMode.PAPER,
        direction=OrderIntent.BUY,
        order_type=OrderType.BRACKET,
        quantity=10,
        filled_quantity=10,
        average_fill_price=100.0,
        limit_price=100.0,
        stop_loss=98.0,
        stop_price=98.0,
        take_profit=104.0,
        status=OrderStatus.FILLED,
        client_order_id="phase6-parent-order",
        broker_order_id="phase6-parent-broker",
        metadata_json={
            "decision": {
                "symbol": "AAPL",
                "thesis": "Breakout continuation",
                "feature_snapshot": {"intraday_volatility_pct": 3.2},
                "structured_events": [
                    {"event_type": "macro_release", "significance": "high"},
                ],
            }
        },
    )
    session.add(parent)
    session.flush()

    child = OrderRecord(
        execution_intent_id=intent.id,
        symbol="AAPL",
        mode=TradingMode.PAPER,
        direction=OrderIntent.SELL,
        order_type=OrderType.LIMIT,
        quantity=10,
        filled_quantity=0,
        average_fill_price=None,
        limit_price=96.0,
        status=OrderStatus.ACCEPTED,
        client_order_id="phase6-child-order",
        broker_order_id="phase6-child-broker",
        parent_order_id=parent.id,
        metadata_json={},
    )
    session.add(child)
    session.commit()

    execution = ExecutionService(session, StubExecutionAdapter())
    created = execution.ingest_broker_fill(
        BrokerFill(
            broker_fill_id="phase6-fill-1",
            broker_order_id="phase6-child-broker",
            symbol="AAPL",
            side="sell",
            quantity=10,
            price=95.0,
            fee=0.0,
            filled_at=datetime.now(UTC),
            raw={},
        ),
        source="unit",
    )
    session.commit()

    cooldown = session.scalar(select(SymbolCooldown).where(SymbolCooldown.symbol == "AAPL"))
    assert created is True
    assert cooldown is not None
    assert cooldown.cooldown_type == "event_failure"
    expires_at = cooldown.expires_at if cooldown.expires_at.tzinfo is not None else cooldown.expires_at.replace(tzinfo=UTC)
    assert expires_at > datetime.now(UTC) + timedelta(minutes=100)
