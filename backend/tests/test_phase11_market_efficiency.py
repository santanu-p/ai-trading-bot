from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from tradingbot.db import Base
from tradingbot.enums import BrokerSlug, OrderIntent, OrderStatus, OrderType, RiskDecision, RunStatus, TimeInForce, TradingMode
from tradingbot.models import AgentRun, BotSettings, ExecutionQualitySample, OrderFill, OrderRecord, RiskEvent, TradeCandidate
from tradingbot.services.adapters import AccountSnapshot, BrokerFill, BrokerOrder, BrokerOrderEvent, BrokerPosition, LiquiditySnapshot, map_alpaca_trade_update
from tradingbot.services.evaluation import DecisionAuditService
from tradingbot.services.execution import ExecutionService
from tradingbot.services.market_efficiency import MarketEfficiencyService

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


class PassiveBroker:
    broker_slug = BrokerSlug.ALPACA

    def get_account_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(equity=100_000, cash=90_000, buying_power=90_000, daily_pl=-250)

    def get_account(self) -> AccountSnapshot:
        return self.get_account_snapshot()

    def list_open_orders(self) -> list[BrokerOrder]:
        return []

    def list_positions(self) -> list[BrokerPosition]:
        return []

    def place_order(self, order):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def replace_order(self, broker_order_id, patch):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def cancel_order(self, broker_order_id: str) -> bool:
        return True

    def cancel_all_orders(self) -> int:
        return 0

    def close_all_positions(self) -> int:
        return 0

    def get_order(self, broker_order_id: str) -> BrokerOrder:
        raise NotImplementedError

    def fetch_fills(self, *, since=None, limit: int = 200, symbol: str | None = None) -> list[BrokerFill]:  # type: ignore[no-untyped-def]
        return []

    def get_liquidity_snapshot(self, symbol: str) -> LiquiditySnapshot | None:
        return None


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()


def _settings(session: Session) -> BotSettings:
    row = BotSettings(
        profile_key="phase11",
        display_name="Phase 11",
        broker_slug=BrokerSlug.ALPACA,
        mode=TradingMode.PAPER,
        broker_permissions=["cash_equity"],
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_phase11_maps_alpaca_trade_update_to_order_event_and_fill() -> None:
    payload = {
        "event": "partial_fill",
        "execution_id": "exec-1",
        "price": "101.25",
        "qty": "3",
        "timestamp": "2026-04-25T14:30:00Z",
        "order": {
            "id": "broker-1",
            "client_order_id": "client-1",
            "symbol": "AAPL",
            "side": "buy",
            "type": "limit",
            "time_in_force": "day",
            "qty": "10",
            "filled_qty": "3",
            "filled_avg_price": "101.25",
            "limit_price": "101.2",
            "status": "partially_filled",
        },
    }

    event = map_alpaca_trade_update(payload)

    assert event.event_id == "exec-1"
    assert event.event_type == "partial_fill"
    assert event.order is not None
    assert event.order.status == OrderStatus.PARTIALLY_FILLED
    assert event.fill is not None
    assert event.fill.quantity == 3
    assert event.fill.price == 101.25


def test_phase11_stream_event_updates_local_order_and_dedupes_fill() -> None:
    session = _session()
    settings = _settings(session)
    order = OrderRecord(
        profile_id=settings.id,
        symbol="AAPL",
        mode=TradingMode.PAPER,
        direction=OrderIntent.BUY,
        order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.DAY,
        quantity=10,
        filled_quantity=0,
        limit_price=100,
        status=OrderStatus.ACCEPTED,
        client_order_id="client-1",
        broker_order_id="broker-1",
        submitted_at=datetime.now(UTC),
        metadata_json={},
    )
    session.add(order)
    session.commit()

    event = BrokerOrderEvent(
        event_id="stream-fill-1",
        event_type="fill",
        order=BrokerOrder(
            broker_order_id="broker-1",
            client_order_id="client-1",
            symbol="AAPL",
            side=OrderIntent.BUY,
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.DAY,
            quantity=10,
            filled_quantity=10,
            average_fill_price=100.5,
            limit_price=100,
            stop_price=None,
            take_profit=None,
            trailing_percent=None,
            trailing_amount=None,
            status=OrderStatus.FILLED,
            status_reason="filled by stream",
            updated_at=datetime.now(UTC),
            raw={"provider": "alpaca_stream"},
        ),
        fill=BrokerFill(
            broker_fill_id="stream-fill-1",
            broker_order_id="broker-1",
            symbol="AAPL",
            side="buy",
            quantity=10,
            price=100.5,
            fee=0.02,
            filled_at=datetime.now(UTC),
            raw={"provider": "alpaca_stream"},
        ),
        raw={},
    )
    service = ExecutionService(session, PassiveBroker(), settings)

    first = service.ingest_broker_stream_event(event)
    second = service.ingest_broker_stream_event(event)
    session.commit()

    session.refresh(order)
    fills = session.scalars(select(OrderFill).where(OrderFill.order_id == order.id)).all()
    assert first == {"events": 1, "order_updates": 1, "fills_ingested": 1, "unknown_orders": 0}
    assert second["fills_ingested"] == 0
    assert order.status == OrderStatus.FILLED
    assert order.filled_quantity == 10
    assert len(fills) == 1


def test_phase11_unknown_stream_order_emits_risk_event() -> None:
    session = _session()
    settings = _settings(session)
    service = ExecutionService(session, PassiveBroker(), settings)

    report = service.ingest_broker_stream_event(
        BrokerOrderEvent(
            event_id="missing-order",
            event_type="fill",
            fill=BrokerFill(
                broker_fill_id="missing-order",
                broker_order_id="broker-missing",
                symbol="MSFT",
                side="buy",
                quantity=1,
                price=250,
                fee=0,
                filled_at=datetime.now(UTC),
                raw={},
            ),
            raw={},
        )
    )

    event = session.scalar(select(RiskEvent).where(RiskEvent.code == "broker_stream_unknown_order"))
    assert report["unknown_orders"] == 1
    assert event is not None
    assert event.payload["broker_order_id"] == "broker-missing"


def test_phase11_market_efficiency_report_summarizes_controls_and_outcomes() -> None:
    session = _session()
    settings = _settings(session)
    now = datetime.now(UTC)
    run = AgentRun(profile_id=settings.id, symbol="AAPL", status=RunStatus.SUCCEEDED, created_at=now)
    session.add(run)
    session.flush()
    session.add_all(
        [
            TradeCandidate(
                profile_id=settings.id,
                run_id=run.id,
                symbol="AAPL",
                direction=OrderIntent.BUY,
                confidence=0.8,
                status="approved",
                thesis="approved",
                entry=100,
                stop_loss=98,
                take_profit=104,
                risk_notes=[],
                raw_payload={},
                created_at=now,
            ),
            TradeCandidate(
                profile_id=settings.id,
                run_id=run.id,
                symbol="MSFT",
                direction=OrderIntent.BUY,
                confidence=0.4,
                status="rejected",
                thesis="rejected",
                entry=100,
                stop_loss=98,
                take_profit=104,
                risk_notes=["risk"],
                raw_payload={},
                created_at=now,
            ),
            RiskEvent(profile_id=settings.id, symbol="MSFT", severity="warning", code="pretrade_rejected", message="blocked", payload={}, created_at=now),
            ExecutionQualitySample(
                profile_id=settings.id,
                order_id=1,
                symbol="AAPL",
                broker_slug=BrokerSlug.ALPACA,
                venue="XNYS",
                order_type=OrderType.LIMIT,
                side=OrderIntent.BUY,
                outcome_status=OrderStatus.FILLED,
                quantity=10,
                filled_quantity=10,
                fill_ratio=1.0,
                realized_slippage_bps=12.5,
                spread_cost=1.1,
                notional=1005,
                quality_score=0.72,
                payload={},
                created_at=now,
            ),
        ]
    )
    session.commit()

    report = MarketEfficiencyService(session, profile_id=settings.id).risk_calibration_report(window_minutes=60)

    assert report["trade_candidates"] == 2
    assert report["approval_rate"] == 0.5
    assert report["rejection_codes"]["pretrade_rejected"] == 1
    assert report["execution_quality"]["avg_quality_score"] == 0.72
    assert report["recommendations"]


def test_phase11_decision_audit_scores_missing_context_and_overconfidence() -> None:
    session = _session()
    settings = _settings(session)
    run = AgentRun(
        profile_id=settings.id,
        symbol="AAPL",
        status=RunStatus.SUCCEEDED,
        model_name="model-a",
        prompt_versions_json={"market": "v1"},
        decision_payload={
            "confidence": 0.95,
            "status": RiskDecision.REJECTED.value,
            "feature_snapshot": {},
            "data_quality": {"passed": False},
            "structured_events": [],
        },
    )
    session.add(run)
    session.commit()

    rows = DecisionAuditService(session, profile_id=settings.id).audit_recent_runs(limit=10)

    assert len(rows) == 1
    assert rows[0]["score"] < 0.75
    assert "missing_feature_snapshot" in rows[0]["issues"]
    assert "overconfident_rejection" in rows[0]["issues"]
