"""FX conversion service for multi-currency portfolio risk.

Provides currency conversion with cached exchange rates for
cross-market position sizing and exposure calculation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tradingbot.enums import Currency
from tradingbot.services.metrics import observe_counter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exchange rate data
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class ExchangeRate:
    """A single exchange rate observation."""

    base: Currency
    quote: Currency
    rate: float
    as_of: datetime
    source: str


# ---------------------------------------------------------------------------
# Hardcoded fallback rates (used when no API is available)
# ---------------------------------------------------------------------------
_FALLBACK_RATES: dict[tuple[str, str], float] = {
    ("USD", "USD"): 1.0,
    ("INR", "INR"): 1.0,
    ("EUR", "EUR"): 1.0,
    ("GBP", "GBP"): 1.0,
    ("JPY", "JPY"): 1.0,
    ("USDT", "USDT"): 1.0,
    ("BTC", "BTC"): 1.0,
    ("USD", "INR"): 83.50,
    ("INR", "USD"): 1 / 83.50,
    ("USD", "EUR"): 0.92,
    ("EUR", "USD"): 1 / 0.92,
    ("USD", "GBP"): 0.79,
    ("GBP", "USD"): 1 / 0.79,
    ("USD", "JPY"): 155.0,
    ("JPY", "USD"): 1 / 155.0,
    ("USDT", "USD"): 1.0,
    ("USD", "USDT"): 1.0,
    ("BTC", "USD"): 65_000.0,
    ("USD", "BTC"): 1 / 65_000.0,
}


# ---------------------------------------------------------------------------
# FX rate cache
# ---------------------------------------------------------------------------
_rate_cache: dict[tuple[str, str], ExchangeRate] = {}
_cache_lock = Lock()
_CACHE_TTL_MINUTES = 60


def _cache_key(base: Currency, quote: Currency) -> tuple[str, str]:
    return (base.value, quote.value)


def _get_cached_rate(base: Currency, quote: Currency) -> ExchangeRate | None:
    key = _cache_key(base, quote)
    with _cache_lock:
        rate = _rate_cache.get(key)
        if rate is None:
            return None
        if (datetime.now(UTC) - rate.as_of) > timedelta(minutes=_CACHE_TTL_MINUTES):
            del _rate_cache[key]
            return None
        return rate


def _set_cached_rate(rate: ExchangeRate) -> None:
    key = _cache_key(rate.base, rate.quote)
    with _cache_lock:
        _rate_cache[key] = rate


# ---------------------------------------------------------------------------
# FX Service
# ---------------------------------------------------------------------------
class FXService:
    """Currency conversion service with caching and fallback rates."""

    def __init__(self, *, base_currency: Currency = Currency.USD) -> None:
        self.base_currency = base_currency

    def convert(
        self,
        amount: float,
        *,
        from_currency: Currency,
        to_currency: Currency,
    ) -> float:
        """Convert an amount from one currency to another."""
        if from_currency == to_currency:
            return amount
        rate = self.get_rate(from_currency, to_currency)
        return round(amount * rate.rate, 6)

    def to_base(self, amount: float, *, from_currency: Currency) -> float:
        """Convert an amount to the base currency (default USD)."""
        return self.convert(
            amount, from_currency=from_currency, to_currency=self.base_currency
        )

    def get_rate(self, base: Currency, quote: Currency) -> ExchangeRate:
        """Get the exchange rate from base to quote currency.

        Uses cache → API → fallback chain.
        """
        if base == quote:
            return ExchangeRate(
                base=base,
                quote=quote,
                rate=1.0,
                as_of=datetime.now(UTC),
                source="identity",
            )

        # Check cache
        cached = _get_cached_rate(base, quote)
        if cached is not None:
            return cached

        # Try inverse cache
        inverse = _get_cached_rate(quote, base)
        if inverse is not None:
            rate = ExchangeRate(
                base=base,
                quote=quote,
                rate=round(1.0 / inverse.rate, 8),
                as_of=inverse.as_of,
                source=f"inverse:{inverse.source}",
            )
            _set_cached_rate(rate)
            return rate

        # Try free API
        api_rate = self._fetch_from_api(base, quote)
        if api_rate is not None:
            _set_cached_rate(api_rate)
            return api_rate

        # Fallback to hardcoded rates
        fallback_value = _FALLBACK_RATES.get((base.value, quote.value))
        if fallback_value is not None:
            rate = ExchangeRate(
                base=base,
                quote=quote,
                rate=fallback_value,
                as_of=datetime.now(UTC),
                source="fallback",
            )
            _set_cached_rate(rate)
            return rate

        # Try triangulation through USD
        if base != Currency.USD and quote != Currency.USD:
            base_to_usd = _FALLBACK_RATES.get((base.value, "USD"))
            usd_to_quote = _FALLBACK_RATES.get(("USD", quote.value))
            if base_to_usd is not None and usd_to_quote is not None:
                triangulated = round(base_to_usd * usd_to_quote, 8)
                rate = ExchangeRate(
                    base=base,
                    quote=quote,
                    rate=triangulated,
                    as_of=datetime.now(UTC),
                    source="triangulated_via_usd",
                )
                _set_cached_rate(rate)
                return rate

        # Last resort
        logger.warning(
            "fx.rate_unavailable",
            extra={"base": base.value, "quote": quote.value},
        )
        return ExchangeRate(
            base=base,
            quote=quote,
            rate=1.0,
            as_of=datetime.now(UTC),
            source="unknown_pair",
        )

    def _fetch_from_api(self, base: Currency, quote: Currency) -> ExchangeRate | None:
        """Try to fetch a rate from a free public FX API."""
        # Using exchangerate.host (free, no key required)
        url = f"https://api.exchangerate.host/convert?from={base.value}&to={quote.value}&amount=1"
        try:
            request = Request(url, method="GET", headers={"Accept": "application/json"})
            with urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                result = data.get("result")
                if result is not None and float(result) > 0:
                    observe_counter(
                        "fx.api_success", tags={"pair": f"{base.value}/{quote.value}"}
                    )
                    return ExchangeRate(
                        base=base,
                        quote=quote,
                        rate=round(float(result), 8),
                        as_of=datetime.now(UTC),
                        source="exchangerate.host",
                    )
        except (HTTPError, URLError, OSError, json.JSONDecodeError, ValueError) as exc:
            observe_counter(
                "fx.api_failure", tags={"pair": f"{base.value}/{quote.value}"}
            )
            logger.debug(
                "fx.api_error",
                extra={"base": base.value, "quote": quote.value, "error": str(exc)},
            )
        return None

    def portfolio_exposure_in_base(
        self,
        positions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Calculate portfolio exposure in base currency.

        Each position dict must have 'symbol', 'market_value', and 'currency'.
        Returns a dict with total_exposure, by_currency breakdown, and
        the FX-adjusted gross exposure.
        """
        total = 0.0
        by_currency: dict[str, float] = {}

        for pos in positions:
            currency_str = str(pos.get("currency", self.base_currency.value))
            try:
                currency = Currency(currency_str)
            except ValueError:
                currency = self.base_currency
            market_value = float(pos.get("market_value", 0.0))
            converted = self.to_base(market_value, from_currency=currency)
            total += abs(converted)
            by_currency[currency_str] = by_currency.get(currency_str, 0.0) + converted

        return {
            "total_exposure_base": round(total, 4),
            "base_currency": self.base_currency.value,
            "by_currency": {k: round(v, 4) for k, v in by_currency.items()},
        }


def clear_rate_cache() -> None:
    """Clear all cached FX rates (useful for testing)."""
    with _cache_lock:
        _rate_cache.clear()
