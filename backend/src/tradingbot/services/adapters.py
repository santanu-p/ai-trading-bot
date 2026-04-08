from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Iterable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tradingbot.config import get_settings
from tradingbot.enums import BrokerSlug, InstrumentClass, OrderIntent, OrderStatus, OrderType, TimeInForce, TradingMode

if TYPE_CHECKING:
    from tradingbot.models import BotSettings


@dataclass(slots=True)
class AccountSnapshot:
    equity: float
    cash: float
    buying_power: float
    daily_pl: float


@dataclass(slots=True)
class BarPoint:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class NewsItem:
    headline: str
    summary: str
    source: str
    created_at: datetime
    sentiment_hint: str


@dataclass(slots=True)
class OrderRequest:
    symbol: str
    quantity: int
    side: OrderIntent = OrderIntent.BUY
    order_type: OrderType = OrderType.LIMIT
    time_in_force: TimeInForce = TimeInForce.DAY
    limit_price: float | None = None
    stop_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    trailing_percent: float | None = None
    trailing_amount: float | None = None
    client_order_id: str | None = None
    allow_extended_hours: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ReplaceOrderRequest:
    quantity: int | None = None
    limit_price: float | None = None
    stop_price: float | None = None
    take_profit: float | None = None
    time_in_force: TimeInForce | None = None


@dataclass(slots=True)
class BrokerOrder:
    broker_order_id: str
    client_order_id: str
    symbol: str
    side: OrderIntent
    order_type: OrderType
    time_in_force: TimeInForce
    quantity: int
    filled_quantity: int
    average_fill_price: float | None
    limit_price: float | None
    stop_price: float | None
    take_profit: float | None
    trailing_percent: float | None
    trailing_amount: float | None
    status: OrderStatus
    status_reason: str | None
    updated_at: datetime | None
    parent_broker_order_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BrokerFill:
    broker_fill_id: str
    broker_order_id: str | None
    symbol: str
    side: str
    quantity: int
    price: float
    fee: float
    filled_at: datetime
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BrokerPosition:
    broker_position_id: str
    symbol: str
    quantity: int
    average_entry_price: float
    market_value: float
    unrealized_pl: float
    side: str
    raw: dict[str, Any] = field(default_factory=dict)


class BrokerAPIError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        category: str = "broker_error",
        retryable: bool = False,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.category = category
        self.retryable = retryable
        self.payload = payload or {}


class ExecutionAdapter(Protocol):
    broker_slug: BrokerSlug

    def get_account_snapshot(self) -> AccountSnapshot:
        ...

    def get_account(self) -> AccountSnapshot:
        ...

    def list_open_orders(self) -> list[BrokerOrder]:
        ...

    def list_positions(self) -> list[BrokerPosition]:
        ...

    def place_order(self, order: OrderRequest) -> BrokerOrder:
        ...

    def replace_order(self, broker_order_id: str, patch: ReplaceOrderRequest) -> BrokerOrder:
        ...

    def cancel_order(self, broker_order_id: str) -> bool:
        ...

    def cancel_all_orders(self) -> int:
        ...

    def close_all_positions(self) -> int:
        ...

    def get_order(self, broker_order_id: str) -> BrokerOrder:
        ...

    def fetch_fills(
        self,
        *,
        since: datetime | None = None,
        limit: int = 200,
        symbol: str | None = None,
    ) -> list[BrokerFill]:
        ...


class MarketDataAdapter(Protocol):
    def get_intraday_bars(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
        interval_minutes: int,
    ) -> list[BarPoint]:
        ...


class NewsAdapter(Protocol):
    def get_recent_news(self, symbol: str, *, limit: int = 10) -> list[NewsItem]:
        ...

    def get_news_between(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
        limit: int = 200,
    ) -> list[NewsItem]:
        ...


class AlpacaRESTMixin:
    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.alpaca_api_key or not self.settings.alpaca_api_secret:
            raise RuntimeError("ALPACA_API_KEY and ALPACA_API_SECRET must be configured.")

    def _request_json(
        self,
        base_url: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        method: str = "GET",
        body: dict[str, Any] | None = None,
    ) -> Any:
        query = f"?{urlencode(params, doseq=True)}" if params else ""
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            f"{base_url}{path}{query}",
            data=data,
            method=method,
            headers={
                "APCA-API-KEY-ID": self.settings.alpaca_api_key,
                "APCA-API-SECRET-KEY": self.settings.alpaca_api_secret,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload) if payload else {}
        except HTTPError as exc:
            payload_text = exc.read().decode("utf-8", errors="ignore")
            payload_json = _safe_json(payload_text)
            raise _normalize_alpaca_error(exc.code, payload_json or {"message": payload_text}) from exc
        except URLError as exc:
            raise BrokerAPIError(
                f"Failed to reach Alpaca API: {exc.reason}",
                category="connectivity",
                retryable=True,
            ) from exc


class AlpacaExecutionAdapter(AlpacaRESTMixin):
    def __init__(self, mode: TradingMode) -> None:
        super().__init__()
        self.broker_slug = BrokerSlug.ALPACA
        self.mode = mode
        self.base_url = (
            self.settings.alpaca_paper_base_url
            if mode == TradingMode.PAPER
            else self.settings.alpaca_live_base_url
        )

    def get_account_snapshot(self) -> AccountSnapshot:
        payload = self._request_json(self.base_url, "/v2/account")
        equity = _to_float(payload.get("equity"))
        last_equity = _to_float(payload.get("last_equity"), fallback=equity)
        return AccountSnapshot(
            equity=equity,
            cash=_to_float(payload.get("cash")),
            buying_power=_to_float(payload.get("buying_power")),
            daily_pl=equity - last_equity,
        )

    def get_account(self) -> AccountSnapshot:
        return self.get_account_snapshot()

    def list_open_orders(self) -> list[BrokerOrder]:
        payload = self._request_json(
            self.base_url,
            "/v2/orders",
            params={"status": "open", "direction": "desc", "nested": "true", "limit": 200},
        )
        if not isinstance(payload, list):
            return []
        return [_map_alpaca_order(item) for item in payload]

    def list_positions(self) -> list[BrokerPosition]:
        payload = self._request_json(self.base_url, "/v2/positions")
        if not isinstance(payload, list):
            return []
        rows: list[BrokerPosition] = []
        for item in payload:
            quantity = int(abs(_to_float(item.get("qty"), fallback=0)))
            side = item.get("side", "long")
            rows.append(
                BrokerPosition(
                    broker_position_id=str(item.get("asset_id") or item.get("symbol") or ""),
                    symbol=str(item.get("symbol") or ""),
                    quantity=quantity,
                    average_entry_price=_to_float(item.get("avg_entry_price")),
                    market_value=abs(_to_float(item.get("market_value"))),
                    unrealized_pl=_to_float(item.get("unrealized_pl")),
                    side=side,
                    raw=item,
                )
            )
        return rows

    def place_order(self, order: OrderRequest) -> BrokerOrder:
        body: dict[str, Any] = {
            "symbol": order.symbol,
            "qty": order.quantity,
            "side": order.side.value,
            "time_in_force": order.time_in_force.value,
            "extended_hours": order.allow_extended_hours,
        }
        if order.client_order_id:
            body["client_order_id"] = order.client_order_id

        if order.order_type == OrderType.MARKET:
            body["type"] = "market"
        elif order.order_type == OrderType.LIMIT:
            body["type"] = "limit"
            body["limit_price"] = _money(order.limit_price)
        elif order.order_type == OrderType.STOP_MARKET:
            body["type"] = "stop"
            body["stop_price"] = _money(order.stop_price)
        elif order.order_type == OrderType.STOP_LIMIT:
            body["type"] = "stop_limit"
            body["limit_price"] = _money(order.limit_price)
            body["stop_price"] = _money(order.stop_price)
        elif order.order_type == OrderType.TRAILING_STOP:
            body["type"] = "trailing_stop"
            if order.trailing_percent is not None:
                body["trail_percent"] = str(order.trailing_percent)
            elif order.trailing_amount is not None:
                body["trail_price"] = _money(order.trailing_amount)
            else:
                raise BrokerAPIError("Trailing stop requires trailing_percent or trailing_amount.", category="validation")
        elif order.order_type in {OrderType.BRACKET, OrderType.OCO}:
            body["order_class"] = "bracket" if order.order_type == OrderType.BRACKET else "oco"
            body["type"] = "limit" if order.limit_price is not None else "market"
            if order.limit_price is not None:
                body["limit_price"] = _money(order.limit_price)
            if order.take_profit is not None:
                body["take_profit"] = {"limit_price": _money(order.take_profit)}
            if order.stop_loss is not None or order.stop_price is not None:
                body["stop_loss"] = {
                    "stop_price": _money(order.stop_loss if order.stop_loss is not None else order.stop_price),
                }
        else:
            raise BrokerAPIError(f"Unsupported order type: {order.order_type.value}", category="validation")

        payload = self._request_json(self.base_url, "/v2/orders", method="POST", body=body)
        return _map_alpaca_order(payload)

    def replace_order(self, broker_order_id: str, patch: ReplaceOrderRequest) -> BrokerOrder:
        body: dict[str, Any] = {}
        if patch.quantity is not None:
            body["qty"] = patch.quantity
        if patch.limit_price is not None:
            body["limit_price"] = _money(patch.limit_price)
        if patch.stop_price is not None:
            body["stop_price"] = _money(patch.stop_price)
        if patch.take_profit is not None:
            body["take_profit"] = {"limit_price": _money(patch.take_profit)}
        if patch.time_in_force is not None:
            body["time_in_force"] = patch.time_in_force.value
        payload = self._request_json(self.base_url, f"/v2/orders/{broker_order_id}", method="PATCH", body=body)
        return _map_alpaca_order(payload)

    def cancel_order(self, broker_order_id: str) -> bool:
        self._request_json(self.base_url, f"/v2/orders/{broker_order_id}", method="DELETE")
        return True

    def cancel_all_orders(self) -> int:
        payload = self._request_json(self.base_url, "/v2/orders", method="DELETE")
        if isinstance(payload, list):
            return len(payload)
        return 0

    def close_all_positions(self) -> int:
        payload = self._request_json(self.base_url, "/v2/positions", method="DELETE")
        if isinstance(payload, list):
            return len(payload)
        return 0

    def get_order(self, broker_order_id: str) -> BrokerOrder:
        payload = self._request_json(self.base_url, f"/v2/orders/{broker_order_id}", params={"nested": "true"})
        return _map_alpaca_order(payload)

    def fetch_fills(
        self,
        *,
        since: datetime | None = None,
        limit: int = 200,
        symbol: str | None = None,
    ) -> list[BrokerFill]:
        params: dict[str, Any] = {
            "activity_types": "FILL",
            "direction": "desc",
            "page_size": max(1, min(limit, 1000)),
        }
        if since is not None:
            params["after"] = since.astimezone(UTC).isoformat().replace("+00:00", "Z")
        if symbol:
            params["symbol"] = symbol

        payload = self._request_json(self.base_url, "/v2/account/activities", params=params)
        if not isinstance(payload, list):
            return []

        fills: list[BrokerFill] = []
        for item in payload:
            fills.append(
                BrokerFill(
                    broker_fill_id=str(item.get("id") or ""),
                    broker_order_id=item.get("order_id"),
                    symbol=str(item.get("symbol") or ""),
                    side=str(item.get("side") or "buy"),
                    quantity=int(abs(_to_float(item.get("qty"), fallback=0))),
                    price=_to_float(item.get("price")),
                    fee=_to_float(item.get("net_amount"), fallback=0.0),
                    filled_at=_to_datetime(item.get("transaction_time")) or datetime.now(UTC),
                    raw=item,
                )
            )
        return fills


class AlpacaMarketDataAdapter(AlpacaRESTMixin):
    def get_intraday_bars(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
        interval_minutes: int,
    ) -> list[BarPoint]:
        params = {
            "symbols": symbol,
            "timeframe": f"{interval_minutes}Min",
            "start": start.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "end": end.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "limit": 200,
            "feed": self.settings.alpaca_market_data_feed,
        }
        payload = self._request_json(self.settings.alpaca_data_base_url, "/v2/stocks/bars", params=params)
        bar_collection = payload.get("bars", {})
        bar_items = bar_collection.get(symbol, []) if isinstance(bar_collection, dict) else bar_collection
        return [
            BarPoint(
                timestamp=datetime.fromisoformat(item["t"].replace("Z", "+00:00")),
                open=float(item["o"]),
                high=float(item["h"]),
                low=float(item["l"]),
                close=float(item["c"]),
                volume=float(item["v"]),
            )
            for item in bar_items
        ]


class AlpacaNewsAdapter(AlpacaRESTMixin):
    def get_recent_news(self, symbol: str, *, limit: int = 10) -> list[NewsItem]:
        params = {"symbols": symbol, "limit": limit, "sort": "desc"}
        payload = self._request_json(self.settings.alpaca_data_base_url, "/v1beta1/news", params=params)
        items = payload.get("news", payload)
        if not isinstance(items, list):
            return []
        return [
            NewsItem(
                headline=item.get("headline", ""),
                summary=item.get("summary", ""),
                source=item.get("source", "alpaca"),
                created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
                sentiment_hint=item.get("headline", ""),
            )
            for item in items
        ]

    def get_news_between(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
        limit: int = 200,
    ) -> list[NewsItem]:
        params = {
            "symbols": symbol,
            "start": start.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "end": end.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "limit": max(1, min(limit, 500)),
            "sort": "asc",
        }
        payload = self._request_json(self.settings.alpaca_data_base_url, "/v1beta1/news", params=params)
        items = payload.get("news", payload)
        if not isinstance(items, list):
            return []
        return [
            NewsItem(
                headline=item.get("headline", ""),
                summary=item.get("summary", ""),
                source=item.get("source", "alpaca"),
                created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
                sentiment_hint=item.get("headline", ""),
            )
            for item in items
        ]


@dataclass(slots=True)
class RouteRequirements:
    instrument_class: InstrumentClass
    required_permissions: tuple[str, ...] = ()


class ExecutionBrokerRouter:
    def __init__(self, settings_row: BotSettings) -> None:
        self._settings_row = settings_row
        self._cache: dict[BrokerSlug, ExecutionAdapter] = {}

    def route(self, requirements: RouteRequirements) -> ExecutionAdapter:
        permissions = {item.lower() for item in (self._settings_row.broker_permissions or [])}
        missing = [perm for perm in requirements.required_permissions if perm.lower() not in permissions]
        if missing:
            raise BrokerAPIError(
                f"Broker account is missing required permissions: {', '.join(missing)}",
                category="routing",
            )

        if self._settings_row.broker_slug == BrokerSlug.ALPACA:
            if requirements.instrument_class not in {InstrumentClass.CASH_EQUITY, InstrumentClass.MIXED}:
                raise BrokerAPIError(
                    f"Alpaca routing does not support instrument class {requirements.instrument_class.value}.",
                    category="routing",
                )
            adapter = self._cache.get(BrokerSlug.ALPACA)
            if adapter is None:
                adapter = AlpacaExecutionAdapter(self._settings_row.mode)
                self._cache[BrokerSlug.ALPACA] = adapter
            return adapter

        raise BrokerAPIError(
            f"Unsupported broker adapter: {self._settings_row.broker_slug.value}",
            category="routing",
        )


def build_broker_adapter(settings_row: BotSettings) -> ExecutionAdapter:
    router = ExecutionBrokerRouter(settings_row)
    instrument_class = settings_row.instrument_class or InstrumentClass.CASH_EQUITY
    return router.route(RouteRequirements(instrument_class=instrument_class))


def build_market_data_adapter(settings_row: BotSettings) -> MarketDataAdapter:
    if settings_row.broker_slug == BrokerSlug.ALPACA:
        return AlpacaMarketDataAdapter()
    raise RuntimeError(f"Unsupported market-data adapter: {settings_row.broker_slug.value}")


def build_news_adapter(settings_row: BotSettings) -> NewsAdapter:
    if settings_row.broker_slug == BrokerSlug.ALPACA:
        return AlpacaNewsAdapter()
    raise RuntimeError(f"Unsupported news adapter: {settings_row.broker_slug.value}")


def _to_float(value: Any, *, fallback: float = 0.0) -> float:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _to_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        raw = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _money(value: float | None) -> float:
    if value is None:
        raise BrokerAPIError("Missing required price value.", category="validation")
    return round(float(value), 4)


def _safe_json(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_alpaca_error(code: int, payload: dict[str, Any]) -> BrokerAPIError:
    message = str(payload.get("message") or payload.get("error") or f"Alpaca API error {code}")
    upper_message = message.upper()

    if code == 403:
        return BrokerAPIError(message, code=code, category="authorization", payload=payload)
    if code == 404:
        return BrokerAPIError(message, code=code, category="not_found", payload=payload)
    if code == 422:
        return BrokerAPIError(message, code=code, category="validation", payload=payload)
    if code in {429, 500, 502, 503, 504}:
        return BrokerAPIError(message, code=code, category="transient", retryable=True, payload=payload)
    if "INSUFFICIENT" in upper_message or "BUYING POWER" in upper_message:
        return BrokerAPIError(message, code=code, category="capital", payload=payload)
    return BrokerAPIError(message, code=code, category="broker_error", payload=payload)


def _map_alpaca_order(payload: dict[str, Any]) -> BrokerOrder:
    raw_status = str(payload.get("status") or "new").lower()
    status_map = {
        "new": OrderStatus.NEW,
        "accepted": OrderStatus.ACCEPTED,
        "pending_new": OrderStatus.ACCEPTED,
        "accepted_for_bidding": OrderStatus.ACCEPTED,
        "stopped": OrderStatus.ACCEPTED,
        "calculated": OrderStatus.ACCEPTED,
        "pending_trigger": OrderStatus.PENDING_TRIGGER,
        "pending_replace": OrderStatus.PENDING_TRIGGER,
        "pending_cancel": OrderStatus.PENDING_TRIGGER,
        "partially_filled": OrderStatus.PARTIALLY_FILLED,
        "filled": OrderStatus.FILLED,
        "done_for_day": OrderStatus.EXPIRED,
        "canceled": OrderStatus.CANCELED,
        "cancelled": OrderStatus.CANCELED,
        "expired": OrderStatus.EXPIRED,
        "replaced": OrderStatus.REPLACED,
        "rejected": OrderStatus.REJECTED,
        "suspended": OrderStatus.SUSPENDED,
    }
    status = status_map.get(raw_status, OrderStatus.NEW)

    order_class = str(payload.get("order_class") or "").lower()
    order_type_raw = str(payload.get("type") or "limit").lower()
    if order_class == "bracket":
        order_type = OrderType.BRACKET
    elif order_class == "oco":
        order_type = OrderType.OCO
    elif order_type_raw == "market":
        order_type = OrderType.MARKET
    elif order_type_raw == "limit":
        order_type = OrderType.LIMIT
    elif order_type_raw == "stop":
        order_type = OrderType.STOP_MARKET
    elif order_type_raw == "stop_limit":
        order_type = OrderType.STOP_LIMIT
    elif order_type_raw == "trailing_stop":
        order_type = OrderType.TRAILING_STOP
    else:
        order_type = OrderType.LIMIT

    tif_raw = str(payload.get("time_in_force") or "day").lower()
    tif_map = {
        "day": TimeInForce.DAY,
        "gtc": TimeInForce.GTC,
        "ioc": TimeInForce.IOC,
        "fok": TimeInForce.FOK,
    }

    return BrokerOrder(
        broker_order_id=str(payload.get("id") or ""),
        client_order_id=str(payload.get("client_order_id") or ""),
        symbol=str(payload.get("symbol") or ""),
        side=OrderIntent(str(payload.get("side") or "buy")),
        order_type=order_type,
        time_in_force=tif_map.get(tif_raw, TimeInForce.DAY),
        quantity=int(abs(_to_float(payload.get("qty"), fallback=0))),
        filled_quantity=int(abs(_to_float(payload.get("filled_qty"), fallback=0))),
        average_fill_price=_to_float(payload.get("filled_avg_price"), fallback=0) or None,
        limit_price=_to_float(payload.get("limit_price"), fallback=0) or None,
        stop_price=_to_float(payload.get("stop_price"), fallback=0) or None,
        take_profit=_extract_take_profit(payload),
        trailing_percent=_to_float(payload.get("trail_percent"), fallback=0) or None,
        trailing_amount=_to_float(payload.get("trail_price"), fallback=0) or None,
        status=status,
        status_reason=payload.get("reject_reason") or payload.get("failure_reason"),
        updated_at=_to_datetime(payload.get("updated_at") or payload.get("submitted_at")),
        parent_broker_order_id=payload.get("parent_order_id"),
        raw=payload,
    )


def _extract_take_profit(payload: dict[str, Any]) -> float | None:
    take_profit = payload.get("take_profit")
    if isinstance(take_profit, dict):
        return _to_float(take_profit.get("limit_price"), fallback=0) or None
    return None
