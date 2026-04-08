from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tradingbot.enums import BrokerSlug, InstrumentClass, OrderStatus, OrderType, TradingMode
from tradingbot.models import BotSettings
from tradingbot.services.adapters import (
    BrokerAPIError,
    ExecutionBrokerRouter,
    RouteRequirements,
    _map_alpaca_order,
    _normalize_alpaca_error,
)


def test_phase9_router_rejects_missing_permissions_before_execution_adapter_creation() -> None:
    settings_row = BotSettings(
        mode=TradingMode.PAPER,
        broker_slug=BrokerSlug.ALPACA,
        broker_permissions=["cash_equity"],
    )
    router = ExecutionBrokerRouter(settings_row)

    with pytest.raises(BrokerAPIError) as raised:
        router.route(
            RouteRequirements(
                instrument_class=InstrumentClass.CASH_EQUITY,
                required_permissions=("options",),
            )
        )

    assert raised.value.category == "routing"


def test_phase9_router_rejects_unsupported_instrument_class_for_alpaca() -> None:
    settings_row = BotSettings(
        mode=TradingMode.PAPER,
        broker_slug=BrokerSlug.ALPACA,
        broker_permissions=["cash_equity"],
    )
    router = ExecutionBrokerRouter(settings_row)

    with pytest.raises(BrokerAPIError) as raised:
        router.route(RouteRequirements(instrument_class=InstrumentClass.FUTURES))

    assert raised.value.category == "routing"


def test_phase9_alpaca_error_normalization_contract() -> None:
    validation = _normalize_alpaca_error(422, {"message": "invalid order"})
    transient = _normalize_alpaca_error(503, {"message": "service unavailable"})
    capital = _normalize_alpaca_error(400, {"message": "insufficient buying power"})

    assert validation.category == "validation"
    assert transient.category == "transient"
    assert transient.retryable is True
    assert capital.category == "capital"


def test_phase9_alpaca_order_payload_maps_to_internal_broker_contract() -> None:
    payload = {
        "id": "alpaca-order-1",
        "client_order_id": "client-1",
        "symbol": "AAPL",
        "side": "buy",
        "order_class": "bracket",
        "type": "limit",
        "time_in_force": "day",
        "qty": "10",
        "filled_qty": "4",
        "filled_avg_price": "100.5",
        "limit_price": "100.3",
        "stop_price": "99.1",
        "status": "partially_filled",
        "updated_at": datetime.now(UTC).isoformat(),
    }

    mapped = _map_alpaca_order(payload)

    assert mapped.broker_order_id == "alpaca-order-1"
    assert mapped.order_type == OrderType.BRACKET
    assert mapped.status == OrderStatus.PARTIALLY_FILLED
    assert mapped.quantity == 10
    assert mapped.filled_quantity == 4
