from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tradingbot.config import get_settings
from tradingbot.enums import BrokerSlug, TradingMode

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
class OrderSubmission:
    symbol: str
    quantity: int
    limit_price: float
    stop_loss: float
    take_profit: float
    client_order_id: str
    side: str = "buy"


class BrokerAdapter(Protocol):
    broker_slug: BrokerSlug

    def get_account(self) -> AccountSnapshot:
        ...

    def submit_bracket_order(self, order: OrderSubmission) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
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
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Alpaca API error {exc.code}: {payload}") from exc
        except URLError as exc:
            raise RuntimeError(f"Failed to reach Alpaca API: {exc.reason}") from exc


class AlpacaBrokerAdapter(AlpacaRESTMixin):
    def __init__(self, mode: TradingMode) -> None:
        super().__init__()
        self.broker_slug = BrokerSlug.ALPACA
        self.mode = mode
        self.base_url = (
            self.settings.alpaca_paper_base_url
            if mode == TradingMode.PAPER
            else self.settings.alpaca_live_base_url
        )

    def get_account(self) -> AccountSnapshot:
        payload = self._request_json(self.base_url, "/v2/account")
        equity = float(payload.get("equity", 0))
        last_equity = float(payload.get("last_equity", equity))
        return AccountSnapshot(
            equity=equity,
            cash=float(payload.get("cash", 0)),
            buying_power=float(payload.get("buying_power", 0)),
            daily_pl=equity - last_equity,
        )

    def submit_bracket_order(self, order: OrderSubmission) -> dict[str, Any]:
        body = {
            "symbol": order.symbol,
            "qty": order.quantity,
            "side": order.side,
            "type": "limit",
            "time_in_force": "day",
            "limit_price": round(order.limit_price, 2),
            "order_class": "bracket",
            "client_order_id": order.client_order_id,
            "take_profit": {"limit_price": round(order.take_profit, 2)},
            "stop_loss": {"stop_price": round(order.stop_loss, 2)},
        }
        return self._request_json(self.base_url, "/v2/orders", method="POST", body=body)


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


def build_broker_adapter(settings_row: BotSettings) -> BrokerAdapter:
    if settings_row.broker_slug == BrokerSlug.ALPACA:
        return AlpacaBrokerAdapter(settings_row.mode)
    raise RuntimeError(f"Unsupported broker adapter: {settings_row.broker_slug.value}")


def build_market_data_adapter(settings_row: BotSettings) -> MarketDataAdapter:
    if settings_row.broker_slug == BrokerSlug.ALPACA:
        return AlpacaMarketDataAdapter()
    raise RuntimeError(f"Unsupported market-data adapter: {settings_row.broker_slug.value}")


def build_news_adapter(settings_row: BotSettings) -> NewsAdapter:
    if settings_row.broker_slug == BrokerSlug.ALPACA:
        return AlpacaNewsAdapter()
    raise RuntimeError(f"Unsupported news adapter: {settings_row.broker_slug.value}")
