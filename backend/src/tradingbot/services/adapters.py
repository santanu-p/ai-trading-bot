from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingbot.config import get_settings
from tradingbot.enums import BrokerSlug, InstrumentClass, OrderIntent, OrderStatus, OrderType, TimeInForce, TradingMode
from tradingbot.services.metrics import observe_counter, observe_duration_ms

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
    reference_price: float | None = None
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


@dataclass(slots=True)
class LiquiditySnapshot:
    symbol: str
    bid_price: float | None
    ask_price: float | None
    bid_size: float | None
    ask_size: float | None
    last_price: float | None
    as_of: datetime | None
    venue: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def mid_price(self) -> float | None:
        if self.bid_price is None or self.ask_price is None:
            return self.last_price
        if self.bid_price <= 0 or self.ask_price <= 0:
            return self.last_price
        return (self.bid_price + self.ask_price) / 2

    @property
    def spread(self) -> float | None:
        if self.bid_price is None or self.ask_price is None:
            return None
        spread = self.ask_price - self.bid_price
        return spread if spread >= 0 else None

    @property
    def spread_bps(self) -> float | None:
        spread = self.spread
        mid = self.mid_price
        if spread is None or mid is None or mid <= 0:
            return None
        return (spread / mid) * 10_000

    @property
    def quoted_depth(self) -> float:
        return max(_to_float(self.bid_size), 0.0) + max(_to_float(self.ask_size), 0.0)


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

    def get_liquidity_snapshot(self, symbol: str) -> LiquiditySnapshot | None:
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
    def __init__(self, *, credential_mode: TradingMode = TradingMode.PAPER) -> None:
        self.settings = get_settings()
        self.credential_mode = credential_mode
        api_key, api_secret = self._credentials()
        if not api_key or not api_secret:
            raise RuntimeError(self._missing_credentials_error())

    def _credentials(self) -> tuple[str | None, str | None]:
        if self.credential_mode == TradingMode.LIVE:
            return self.settings.live_broker_credentials()
        return self.settings.paper_broker_credentials()

    def _missing_credentials_error(self) -> str:
        if self.credential_mode == TradingMode.LIVE:
            return (
                "Live Alpaca credentials are missing. Configure "
                "ALPACA_LIVE_API_KEY/ALPACA_LIVE_API_SECRET or ALPACA_API_KEY/ALPACA_API_SECRET fallback."
            )
        return (
            "Paper Alpaca credentials are missing. Configure "
            "ALPACA_PAPER_API_KEY/ALPACA_PAPER_API_SECRET or ALPACA_API_KEY/ALPACA_API_SECRET fallback."
        )

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
        api_key, api_secret = self._credentials()
        if api_key is None or api_secret is None:
            raise RuntimeError(self._missing_credentials_error())
        request = Request(
            f"{base_url}{path}{query}",
            data=data,
            method=method,
            headers={
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": api_secret,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        started = perf_counter()
        method_tag = method.upper().strip() or "GET"
        try:
            with urlopen(request, timeout=20) as response:
                payload = response.read().decode("utf-8")
                observe_counter(
                    "external.alpaca.requests",
                    tags={"method": method_tag, "path": path, "status": "success"},
                )
                return json.loads(payload) if payload else {}
        except HTTPError as exc:
            payload_text = exc.read().decode("utf-8", errors="ignore")
            payload_json = _safe_json(payload_text)
            observe_counter(
                "external.alpaca.requests",
                tags={"method": method_tag, "path": path, "status": "error", "code": str(exc.code)},
            )
            raise _normalize_alpaca_error(exc.code, payload_json or {"message": payload_text}) from exc
        except URLError as exc:
            observe_counter(
                "external.alpaca.requests",
                tags={"method": method_tag, "path": path, "status": "error", "code": "url_error"},
            )
            raise BrokerAPIError(
                f"Failed to reach Alpaca API: {exc.reason}",
                category="connectivity",
                retryable=True,
            ) from exc
        finally:
            observe_duration_ms(
                "external.alpaca.latency_ms",
                duration_ms=(perf_counter() - started) * 1000,
                tags={"method": method_tag, "path": path},
            )


class AlpacaExecutionAdapter(AlpacaRESTMixin):
    def __init__(self, mode: TradingMode) -> None:
        super().__init__(credential_mode=mode)
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
                    fee=_to_float(item.get("fee"), fallback=0.0),
                    filled_at=_to_datetime(item.get("transaction_time")) or datetime.now(UTC),
                    raw=item,
                )
            )
        return fills

    def get_liquidity_snapshot(self, symbol: str) -> LiquiditySnapshot | None:
        normalized_symbol = symbol.upper().strip()
        if not normalized_symbol:
            return None

        params = {
            "symbols": normalized_symbol,
            "feed": self.settings.alpaca_market_data_feed,
        }
        try:
            quote_payload = self._request_json(self.settings.alpaca_data_base_url, "/v2/stocks/quotes/latest", params=params)
        except BrokerAPIError:
            return None

        quotes = quote_payload.get("quotes", {}) if isinstance(quote_payload, dict) else {}
        quote = quotes.get(normalized_symbol) if isinstance(quotes, dict) else None
        if not isinstance(quote, dict):
            return None

        trade_payload: dict[str, Any] = {}
        try:
            trade_payload = self._request_json(self.settings.alpaca_data_base_url, "/v2/stocks/trades/latest", params=params)
        except BrokerAPIError:
            trade_payload = {}
        trades = trade_payload.get("trades", {}) if isinstance(trade_payload, dict) else {}
        trade = trades.get(normalized_symbol) if isinstance(trades, dict) else {}
        trade_dict = trade if isinstance(trade, dict) else {}

        return LiquiditySnapshot(
            symbol=normalized_symbol,
            bid_price=_to_float(quote.get("bp"), fallback=0) or None,
            ask_price=_to_float(quote.get("ap"), fallback=0) or None,
            bid_size=_to_float(quote.get("bs"), fallback=0) or None,
            ask_size=_to_float(quote.get("as"), fallback=0) or None,
            last_price=_to_float(trade_dict.get("p"), fallback=0) or None,
            as_of=_to_datetime(quote.get("t") or trade_dict.get("t")),
            venue=str(quote.get("ax") or quote.get("bx") or "").strip() or None,
            raw={"quote": quote, "trade": trade_dict},
        )


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


class ImportedFileStore:
    def __init__(self, root: str | Path | None = None) -> None:
        settings = get_settings()
        self.root = Path(root or settings.india_import_root)
        self.bars_dir = self.root / "bars"
        self.aggregate_bars_json = self.root / "bars.json"
        self.news_json = self.root / "news.json"

    def load_bars(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
    ) -> list[BarPoint]:
        rows = self._read_symbol_bar_rows(symbol)
        points = [_bar_from_row(item) for item in rows]
        return [
            point
            for point in sorted(points, key=lambda item: item.timestamp)
            if start <= point.timestamp <= end
        ]

    def latest_price(self, symbol: str) -> tuple[float | None, datetime | None]:
        rows = self._read_symbol_bar_rows(symbol)
        if not rows:
            return None, None
        latest = max((_bar_from_row(item) for item in rows), key=lambda item: item.timestamp, default=None)
        if latest is None:
            return None, None
        return latest.close, latest.timestamp

    def load_news(
        self,
        symbol: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[NewsItem]:
        if not self.news_json.exists():
            return []
        try:
            payload = json.loads(self.news_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        rows = payload if isinstance(payload, list) else []
        normalized_symbol = symbol.upper().strip()
        items: list[NewsItem] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            symbols = {str(raw).upper().strip() for raw in item.get("symbols", []) if str(raw).strip()}
            if symbols and normalized_symbol not in symbols:
                continue
            created_at = _to_datetime(item.get("created_at"))
            if created_at is None:
                continue
            if start is not None and created_at < start:
                continue
            if end is not None and created_at > end:
                continue
            items.append(
                NewsItem(
                    headline=str(item.get("headline") or ""),
                    summary=str(item.get("summary") or ""),
                    source=str(item.get("source") or "imported"),
                    created_at=created_at,
                    sentiment_hint=str(item.get("sentiment_hint") or item.get("headline") or ""),
                )
            )
        items.sort(key=lambda entry: entry.created_at, reverse=start is None and end is None)
        return items[: max(limit, 1)]

    def _read_symbol_bar_rows(self, symbol: str) -> list[dict[str, Any]]:
        normalized_symbol = symbol.upper().strip()
        symbol_stem = _sanitize_symbol_filename(normalized_symbol)
        for candidate in [self.bars_dir / f"{symbol_stem}.json", self.bars_dir / f"{symbol_stem}.csv"]:
            if not candidate.exists():
                continue
            if candidate.suffix == ".json":
                try:
                    payload = json.loads(candidate.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    return []
                return payload if isinstance(payload, list) else []
            with candidate.open("r", encoding="utf-8", newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)]

        if self.aggregate_bars_json.exists():
            try:
                payload = json.loads(self.aggregate_bars_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return []
            if isinstance(payload, dict):
                rows = payload.get(normalized_symbol, [])
                return rows if isinstance(rows, list) else []
        return []


class IndiaImportedMarketDataAdapter:
    def __init__(self, store: ImportedFileStore | None = None) -> None:
        self.store = store or ImportedFileStore()

    def get_intraday_bars(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
        interval_minutes: int,
    ) -> list[BarPoint]:
        del interval_minutes
        return self.store.load_bars(symbol, start=start, end=end)


class IndiaImportedNewsAdapter:
    def __init__(self, store: ImportedFileStore | None = None) -> None:
        self.store = store or ImportedFileStore()

    def get_recent_news(self, symbol: str, *, limit: int = 10) -> list[NewsItem]:
        return self.store.load_news(symbol, limit=limit)

    def get_news_between(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
        limit: int = 200,
    ) -> list[NewsItem]:
        return self.store.load_news(symbol, start=start, end=end, limit=limit)


class IndiaPaperExecutionAdapter:
    def __init__(self, session: Session, settings_row: BotSettings, store: ImportedFileStore | None = None) -> None:
        self.session = session
        self.settings_row = settings_row
        self.store = store or ImportedFileStore()
        self.broker_slug = BrokerSlug.INTERNAL_PAPER

    def get_account_snapshot(self) -> AccountSnapshot:
        from tradingbot.models import PositionRecord

        positions = self.session.scalars(
            select(PositionRecord).where(PositionRecord.profile_id == self.settings_row.id)
        ).all()
        equity = 1_000_000.0
        exposure = sum(max(position.market_value, 0.0) for position in positions)
        daily_pl = sum(position.unrealized_pl for position in positions)
        cash = max(equity - exposure, 0.0)
        return AccountSnapshot(equity=equity, cash=cash, buying_power=cash, daily_pl=daily_pl)

    def get_account(self) -> AccountSnapshot:
        return self.get_account_snapshot()

    def list_open_orders(self) -> list[BrokerOrder]:
        from tradingbot.models import OrderRecord

        rows = self.session.scalars(
            select(OrderRecord)
            .where(OrderRecord.profile_id == self.settings_row.id)
            .where(OrderRecord.status.notin_((OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED)))
            .order_by(OrderRecord.created_at.desc())
        ).all()
        return [_map_local_order(row) for row in rows]

    def list_positions(self) -> list[BrokerPosition]:
        from tradingbot.models import PositionRecord

        rows = self.session.scalars(
            select(PositionRecord).where(PositionRecord.profile_id == self.settings_row.id).order_by(PositionRecord.symbol.asc())
        ).all()
        return [
            BrokerPosition(
                broker_position_id=row.broker_position_id or f"position-{row.id}",
                symbol=row.symbol,
                quantity=row.quantity,
                average_entry_price=row.average_entry_price,
                market_value=row.market_value,
                unrealized_pl=row.unrealized_pl,
                side=row.side,
                raw={"profile_id": row.profile_id},
            )
            for row in rows
        ]

    def place_order(self, order: OrderRequest) -> BrokerOrder:
        fill_price, filled_at = self.store.latest_price(order.symbol)
        if fill_price is None:
            raise BrokerAPIError(
                f"No imported India bar data found for {order.symbol}.",
                category="validation",
            )
        broker_order_id = f"india-paper-{uuid4().hex[:18]}"
        return BrokerOrder(
            broker_order_id=broker_order_id,
            client_order_id=order.client_order_id or broker_order_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            time_in_force=order.time_in_force,
            quantity=order.quantity,
            filled_quantity=order.quantity,
            average_fill_price=round(fill_price, 4),
            limit_price=order.limit_price,
            stop_price=order.stop_price,
            take_profit=order.take_profit,
            trailing_percent=order.trailing_percent,
            trailing_amount=order.trailing_amount,
            status=OrderStatus.FILLED,
            status_reason="Filled by India paper simulator using imported market data.",
            updated_at=filled_at or datetime.now(UTC),
            raw={
                "provider": "india_paper",
                "fill_id": f"fill-{broker_order_id}",
                "fill_price": round(fill_price, 4),
                "fill_qty": order.quantity,
                "filled_at": (filled_at or datetime.now(UTC)).astimezone(UTC).isoformat(),
            },
        )

    def replace_order(self, broker_order_id: str, patch: ReplaceOrderRequest) -> BrokerOrder:
        return self.get_order(broker_order_id)

    def cancel_order(self, broker_order_id: str) -> bool:
        del broker_order_id
        return True

    def cancel_all_orders(self) -> int:
        return len(self.list_open_orders())

    def close_all_positions(self) -> int:
        return len(self.list_positions())

    def get_order(self, broker_order_id: str) -> BrokerOrder:
        from tradingbot.models import OrderRecord

        row = self.session.scalar(
            select(OrderRecord)
            .where(OrderRecord.profile_id == self.settings_row.id)
            .where(OrderRecord.broker_order_id == broker_order_id)
        )
        if row is None:
            raise BrokerAPIError("India paper order was not found.", code=404, category="not_found")
        return _map_local_order(row)

    def fetch_fills(
        self,
        *,
        since: datetime | None = None,
        limit: int = 200,
        symbol: str | None = None,
    ) -> list[BrokerFill]:
        del since, limit, symbol
        return []

    def get_liquidity_snapshot(self, symbol: str) -> LiquiditySnapshot | None:
        price, as_of = self.store.latest_price(symbol)
        if price is None:
            return None
        return LiquiditySnapshot(
            symbol=symbol.upper().strip(),
            bid_price=round(price * 0.9995, 4),
            ask_price=round(price * 1.0005, 4),
            bid_size=1000,
            ask_size=1000,
            last_price=round(price, 4),
            as_of=as_of,
            venue=self.settings_row.broker_venue,
            raw={"provider": "india_paper"},
        )


@dataclass(slots=True)
class RouteRequirements:
    instrument_class: InstrumentClass
    required_permissions: tuple[str, ...] = ()


class ExecutionBrokerRouter:
    def __init__(self, session: Session | BotSettings | None, settings_row: BotSettings | None = None) -> None:
        if settings_row is None:
            if session is None:
                raise TypeError("ExecutionBrokerRouter requires a BotSettings row.")
            self._session = None
            self._settings_row = session
        else:
            self._session = session if isinstance(session, Session) else None
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
        if self._settings_row.broker_slug == BrokerSlug.INTERNAL_PAPER:
            adapter = self._cache.get(BrokerSlug.INTERNAL_PAPER)
            if adapter is None:
                if self._session is None:
                    raise BrokerAPIError(
                        "India paper routing requires a database session.",
                        category="routing",
                    )
                adapter = IndiaPaperExecutionAdapter(self._session, self._settings_row)
                self._cache[BrokerSlug.INTERNAL_PAPER] = adapter
            return adapter

        raise BrokerAPIError(
            f"Unsupported broker adapter: {self._settings_row.broker_slug.value}",
            category="routing",
        )


def build_broker_adapter(session: Session | None, settings_row: BotSettings) -> ExecutionAdapter:
    router = ExecutionBrokerRouter(session, settings_row)
    instrument_class = settings_row.instrument_class or InstrumentClass.CASH_EQUITY
    return router.route(RouteRequirements(instrument_class=instrument_class))


def build_market_data_adapter(settings_row: BotSettings) -> MarketDataAdapter:
    if settings_row.broker_slug == BrokerSlug.ALPACA:
        return AlpacaMarketDataAdapter()
    if settings_row.broker_slug == BrokerSlug.INTERNAL_PAPER:
        return IndiaImportedMarketDataAdapter()
    raise RuntimeError(f"Unsupported market-data adapter: {settings_row.broker_slug.value}")


def build_news_adapter(settings_row: BotSettings) -> NewsAdapter:
    if settings_row.broker_slug == BrokerSlug.ALPACA:
        return AlpacaNewsAdapter()
    if settings_row.broker_slug == BrokerSlug.INTERNAL_PAPER:
        return IndiaImportedNewsAdapter()
    raise RuntimeError(f"Unsupported news adapter: {settings_row.broker_slug.value}")


def _sanitize_symbol_filename(symbol: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in symbol.upper().strip())


def _bar_from_row(row: dict[str, Any]) -> BarPoint:
    return BarPoint(
        timestamp=_to_datetime(row.get("timestamp") or row.get("t")) or datetime.now(UTC),
        open=_to_float(row.get("open") or row.get("o")),
        high=_to_float(row.get("high") or row.get("h")),
        low=_to_float(row.get("low") or row.get("l")),
        close=_to_float(row.get("close") or row.get("c")),
        volume=_to_float(row.get("volume") or row.get("v")),
    )


def _map_local_order(row) -> BrokerOrder:
    return BrokerOrder(
        broker_order_id=str(row.broker_order_id or f"local-{row.id}"),
        client_order_id=row.client_order_id,
        symbol=row.symbol,
        side=row.direction,
        order_type=row.order_type,
        time_in_force=row.time_in_force,
        quantity=row.quantity,
        filled_quantity=row.filled_quantity,
        average_fill_price=row.average_fill_price,
        limit_price=row.limit_price,
        stop_price=row.stop_price,
        take_profit=row.take_profit,
        trailing_percent=row.trailing_percent,
        trailing_amount=row.trailing_amount,
        status=row.status,
        status_reason=row.status_reason,
        updated_at=row.last_broker_update_at,
        raw={"profile_id": row.profile_id, "order_id": row.id},
    )


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
