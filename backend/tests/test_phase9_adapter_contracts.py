from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tradingbot.config import Settings
from tradingbot.enums import (
    BrokerSlug,
    InstrumentClass,
    OrderStatus,
    OrderType,
    TradingMode,
)
from tradingbot.models import BotSettings
from tradingbot.services.adapters import (
    AlpacaExecutionAdapter,
    BrokerAPIError,
    ExecutionBrokerRouter,
    RouteRequirements,
    _map_alpaca_order,
    _normalize_alpaca_error,
)


def test_phase9_router_rejects_missing_permissions_before_execution_adapter_creation() -> (
    None
):
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


def test_phase9_fetch_fills_maps_fee_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tradingbot.services.adapters.get_settings",
        lambda: Settings(
            alpaca_paper_api_key="test-paper-key",
            alpaca_paper_api_secret="test-paper-secret",
        ),
    )
    adapter = AlpacaExecutionAdapter(TradingMode.PAPER)

    def _fake_request_json(  # type: ignore[no-untyped-def]
        base_url: str,
        path: str,
        *,
        params=None,
        method: str = "GET",
        body=None,
    ):
        del base_url, path, params, method, body
        return [
            {
                "id": "fill-1",
                "order_id": "order-1",
                "symbol": "AAPL",
                "side": "buy",
                "qty": "2",
                "price": "100.5",
                "fee": "0.12",
                "net_amount": "-201.00",
                "transaction_time": datetime.now(UTC).isoformat(),
            }
        ]

    monkeypatch.setattr(adapter, "_request_json", _fake_request_json)
    fills = adapter.fetch_fills(limit=5)

    assert len(fills) == 1
    assert fills[0].fee == pytest.approx(0.12)


def test_phase9_india_paper_adapter_fills_nse_order_from_imported_bars(
    tmp_path,
) -> None:
    from tradingbot.enums import OrderIntent, TimeInForce
    from tradingbot.services.adapters import (
        ImportedFileStore,
        IndiaPaperExecutionAdapter,
        OrderRequest,
    )

    bars_dir = tmp_path / "bars"
    bars_dir.mkdir()
    (bars_dir / "RELIANCE_NSE.json").write_text(
        """
        [
          {"timestamp": "2026-05-14T03:45:00+00:00", "open": 2830.0, "high": 2842.5, "low": 2826.0, "close": 2838.75, "volume": 1250000}
        ]
        """.strip(),
        encoding="utf-8",
    )
    settings_row = BotSettings(
        id=7,
        broker_slug=BrokerSlug.INTERNAL_PAPER,
        broker_venue="NSE",
        mode=TradingMode.PAPER,
    )
    adapter = IndiaPaperExecutionAdapter(
        None, settings_row, store=ImportedFileStore(tmp_path)
    )  # type: ignore[arg-type]

    order = adapter.place_order(
        OrderRequest(
            symbol="RELIANCE.NSE",
            quantity=3,
            side=OrderIntent.BUY,
            time_in_force=TimeInForce.DAY,
            client_order_id="india-test-1",
        )
    )

    assert order.status == OrderStatus.FILLED
    assert order.average_fill_price == 2838.75
    assert order.raw["provider"] == "india_paper"
    assert order.raw["fill_qty"] == 3
