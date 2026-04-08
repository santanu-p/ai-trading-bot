from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tradingbot.db import Base
from tradingbot.enums import BrokerSlug, InstrumentClass, OrderIntent, OrderStatus, OrderType, RiskDecision, TimeInForce, TradingMode
from tradingbot.models import BotSettings, ReconciliationMismatch
from tradingbot.schemas.trading import CommitteeDecision, RiskCheckResult
from tradingbot.services.adapters import (
    AccountSnapshot,
    BrokerAPIError,
    BrokerFill,
    BrokerOrder,
    BrokerPosition,
    OrderRequest,
    ReplaceOrderRequest,
)
from tradingbot.services.contracts import ContractMasterService
from tradingbot.services.execution import ExecutionService
from tradingbot.services.pretrade import PreTradeValidator
from tradingbot.services.reconciliation import ReconciliationService


class FakeExecutionAdapter:
    broker_slug = BrokerSlug.ALPACA

    def __init__(self) -> None:
        self._orders: dict[str, BrokerOrder] = {}
        self._fills: list[BrokerFill] = []

    def get_account_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(equity=100_000, cash=100_000, buying_power=100_000, daily_pl=0)

    def get_account(self) -> AccountSnapshot:
        return self.get_account_snapshot()

    def list_open_orders(self) -> list[BrokerOrder]:
        return [order for order in self._orders.values() if order.status not in {OrderStatus.FILLED, OrderStatus.CANCELED}]

    def list_positions(self) -> list[BrokerPosition]:
        return []

    def place_order(self, order: OrderRequest) -> BrokerOrder:
        broker_order_id = f"broker-{order.client_order_id or 'id'}"
        broker_order = BrokerOrder(
            broker_order_id=broker_order_id,
            client_order_id=order.client_order_id or "",
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
            raw={"id": broker_order_id},
        )
        self._orders[broker_order_id] = broker_order
        return broker_order

    def replace_order(self, broker_order_id: str, patch: ReplaceOrderRequest) -> BrokerOrder:
        order = self._orders[broker_order_id]
        order.limit_price = patch.limit_price if patch.limit_price is not None else order.limit_price
        order.stop_price = patch.stop_price if patch.stop_price is not None else order.stop_price
        order.quantity = patch.quantity if patch.quantity is not None else order.quantity
        order.status = OrderStatus.REPLACED
        order.updated_at = datetime.now(UTC)
        return order

    def cancel_order(self, broker_order_id: str) -> bool:
        order = self._orders[broker_order_id]
        order.status = OrderStatus.CANCELED
        order.updated_at = datetime.now(UTC)
        return True

    def cancel_all_orders(self) -> int:
        count = 0
        for order in self._orders.values():
            if order.status not in {OrderStatus.CANCELED, OrderStatus.FILLED}:
                order.status = OrderStatus.CANCELED
                count += 1
        return count

    def close_all_positions(self) -> int:
        return 0

    def get_order(self, broker_order_id: str) -> BrokerOrder:
        if broker_order_id not in self._orders:
            raise BrokerAPIError("not found", code=404, category="not_found")
        return self._orders[broker_order_id]

    def fetch_fills(
        self,
        *,
        since: datetime | None = None,
        limit: int = 200,
        symbol: str | None = None,
    ) -> list[BrokerFill]:
        rows = self._fills
        if since is not None:
            rows = [row for row in rows if row.filled_at > since]
        if symbol:
            rows = [row for row in rows if row.symbol == symbol]
        return rows[:limit]


class MismatchAdapter(FakeExecutionAdapter):
    def list_open_orders(self) -> list[BrokerOrder]:
        return [
            BrokerOrder(
                broker_order_id="external-open-order",
                client_order_id="external-client-id",
                symbol="MSFT",
                side=OrderIntent.BUY,
                order_type=OrderType.LIMIT,
                time_in_force=TimeInForce.DAY,
                quantity=10,
                filled_quantity=0,
                average_fill_price=None,
                limit_price=410,
                stop_price=None,
                take_profit=None,
                trailing_percent=None,
                trailing_amount=None,
                status=OrderStatus.ACCEPTED,
                status_reason=None,
                updated_at=datetime.now(UTC),
                raw={"id": "external-open-order"},
            )
        ]



def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()



def _approved_decision(symbol: str = "MSFT") -> CommitteeDecision:
    return CommitteeDecision(
        symbol=symbol,
        direction=OrderIntent.BUY,
        confidence=0.79,
        entry=410,
        stop_loss=405,
        take_profit=420,
        time_horizon="intraday",
        status=RiskDecision.APPROVED,
        thesis="Momentum and catalyst aligned.",
        risk_notes=[],
    )



def test_submit_trade_persists_state_machine_transitions() -> None:
    session = _session()
    service = ExecutionService(session, FakeExecutionAdapter())

    order = service.submit_trade(
        mode=TradingMode.PAPER,
        decision=_approved_decision(),
        risk_result=RiskCheckResult(decision=RiskDecision.APPROVED, approved_quantity=10, notes=[]),
    )

    assert order is not None
    assert order.status == OrderStatus.ACCEPTED
    transitions = service.list_order_transitions(order.id)
    assert [item.to_status for item in transitions] == [OrderStatus.NEW, OrderStatus.ACCEPTED]



def test_ingest_fill_moves_order_partial_then_filled() -> None:
    session = _session()
    service = ExecutionService(session, FakeExecutionAdapter())
    order = service.submit_trade(
        mode=TradingMode.PAPER,
        decision=_approved_decision("AAPL"),
        risk_result=RiskCheckResult(decision=RiskDecision.APPROVED, approved_quantity=10, notes=[]),
    )
    assert order is not None

    first_fill = BrokerFill(
        broker_fill_id="fill-1",
        broker_order_id=order.broker_order_id,
        symbol=order.symbol,
        side="buy",
        quantity=4,
        price=410,
        fee=0,
        filled_at=datetime.now(UTC),
        raw={},
    )
    second_fill = BrokerFill(
        broker_fill_id="fill-2",
        broker_order_id=order.broker_order_id,
        symbol=order.symbol,
        side="buy",
        quantity=6,
        price=411,
        fee=0,
        filled_at=datetime.now(UTC) + timedelta(seconds=1),
        raw={},
    )

    assert service.ingest_broker_fill(first_fill, source="unit") is True
    session.commit()
    assert service.ingest_broker_fill(second_fill, source="unit") is True
    session.commit()

    refreshed = session.get(type(order), order.id)
    assert refreshed is not None
    assert refreshed.filled_quantity == 10
    assert refreshed.status == OrderStatus.FILLED



def test_pretrade_validator_rejects_tick_lot_and_capital_violations() -> None:
    session = _session()
    contract_master = ContractMasterService(session)
    contract_master.upsert_contract(
        symbol="ESU6",
        instrument_class=InstrumentClass.FUTURES,
        tick_size=0.25,
        lot_size=5,
        contract_multiplier=50.0,
        shortable=True,
        option_chain_available=False,
        metadata_json={"margin_rate": 1.0},
    )

    validator = PreTradeValidator(session, contract_master)
    result = validator.validate(
        order=OrderRequest(symbol="ESU6", quantity=3, side=OrderIntent.BUY, order_type=OrderType.LIMIT, limit_price=5200.12),
        instrument_class=InstrumentClass.FUTURES,
        account=AccountSnapshot(equity=1_000, cash=500, buying_power=500, daily_pl=0),
    )

    assert result.accepted is False
    assert any("lot size" in reason.lower() for reason in result.reasons)
    assert any("tick size" in reason.lower() for reason in result.reasons)
    assert any("buying power" in reason.lower() for reason in result.reasons)



def test_reconciliation_flags_missing_local_order_and_pauses_live_mode() -> None:
    session = _session()
    settings_row = BotSettings(mode=TradingMode.LIVE, broker_slug=BrokerSlug.ALPACA, kill_switch_enabled=False)
    session.add(settings_row)
    session.commit()

    execution = ExecutionService(session, MismatchAdapter())
    report = ReconciliationService(
        session=session,
        settings_row=settings_row,
        execution=execution,
        adapter=execution.broker,
    ).reconcile()

    assert report.mismatches_created >= 1
    assert report.unresolved_mismatches >= 1
    assert report.live_paused is True
    assert settings_row.kill_switch_enabled is True
    mismatch_count = session.query(ReconciliationMismatch).count()
    assert mismatch_count >= 1
