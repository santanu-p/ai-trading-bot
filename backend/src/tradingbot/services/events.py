from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Any

from tradingbot.services.adapters import NewsItem
from tradingbot.services.features import IndexContext

EARNINGS_TERMS = {"earnings", "guidance", "eps", "revenue", "results", "after close", "before open"}
ANALYST_TERMS = {"upgrade", "downgrade", "price target", "initiates", "overweight", "underweight"}
MACRO_TERMS = {"cpi", "inflation", "fomc", "federal reserve", "interest rate", "nfp", "jobs report", "gdp", "pmi"}

SECTOR_ETF_MAP: dict[str, str] = {
    "AAPL": "XLK",
    "MSFT": "XLK",
    "NVDA": "SMH",
    "AMD": "SMH",
    "AMZN": "XLY",
    "TSLA": "XLY",
    "META": "XLC",
    "GOOGL": "XLC",
    "JPM": "XLF",
    "BAC": "XLF",
    "XOM": "XLE",
    "CVX": "XLE",
    "UNH": "XLV",
    "PFE": "XLV",
}

WEEKLY_CALENDAR_EVENTS: tuple[tuple[str, str, int, int, int, str], ...] = (
    ("jobless_claims", "US Initial Jobless Claims", 3, 13, 30, "high"),
    ("consumer_sentiment", "US Michigan Consumer Sentiment", 4, 14, 0, "medium"),
    ("crude_inventories", "EIA Crude Oil Inventories", 2, 14, 30, "medium"),
)


@dataclass(slots=True)
class StructuredEvent:
    event_type: str
    title: str
    event_time: datetime | None
    significance: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "title": self.title,
            "event_time": self.event_time.astimezone(UTC).isoformat() if self.event_time else None,
            "significance": self.significance,
            "source": self.source,
            "payload": self.payload,
        }


def extract_structured_events(
    symbol: str,
    news_items: list[NewsItem],
    *,
    as_of: datetime,
    index_context: IndexContext | None = None,
    lookahead_hours: int = 48,
) -> list[StructuredEvent]:
    normalized_now = _utc(as_of)
    events: list[StructuredEvent] = []
    seen: set[tuple[str, str]] = set()
    ordered_news = sorted(news_items, key=lambda item: item.created_at, reverse=True)

    for item in ordered_news[:40]:
        text = f"{item.headline} {item.summary}".lower()
        for event_type in _classify_news_event_types(text):
            key = (event_type, item.headline.strip().lower())
            if key in seen:
                continue
            seen.add(key)
            events.append(
                StructuredEvent(
                    event_type=event_type,
                    title=item.headline.strip() or f"{symbol} news event",
                    event_time=_utc(item.created_at),
                    significance="high" if event_type in {"earnings_date", "macro_release"} else "medium",
                    source=item.source or "news",
                    payload={
                        "symbol": symbol,
                        "summary": item.summary,
                    },
                )
            )

    sector_proxy = SECTOR_ETF_MAP.get(symbol.upper())
    if sector_proxy is not None:
        events.append(
            StructuredEvent(
                event_type="sector_etf_context",
                title=f"{symbol.upper()} sector proxy: {sector_proxy}",
                event_time=normalized_now,
                significance="medium",
                source="internal",
                payload={
                    "symbol": symbol.upper(),
                    "sector_etf": sector_proxy,
                    "market_regime": index_context.regime if index_context else "neutral",
                },
            )
        )

    for event in _upcoming_calendar_events(normalized_now, lookahead_hours=lookahead_hours):
        events.append(event)

    return sorted(events, key=lambda item: (item.event_time or normalized_now))


def serialize_structured_events(events: list[StructuredEvent]) -> list[dict[str, Any]]:
    return [event.to_payload() for event in events]


def _classify_news_event_types(text: str) -> list[str]:
    event_types: list[str] = []
    if any(token in text for token in EARNINGS_TERMS):
        event_types.append("earnings_date")
    if any(token in text for token in ANALYST_TERMS):
        event_types.append("analyst_action")
    if any(token in text for token in MACRO_TERMS):
        event_types.append("macro_release")
    return event_types


def _upcoming_calendar_events(now: datetime, *, lookahead_hours: int) -> list[StructuredEvent]:
    horizon = now + timedelta(hours=max(lookahead_hours, 1))
    events: list[StructuredEvent] = []
    for code, title, weekday, hour, minute, significance in WEEKLY_CALENDAR_EVENTS:
        next_time = _next_weekday_time(now, weekday=weekday, hour=hour, minute=minute)
        if next_time <= horizon:
            events.append(
                StructuredEvent(
                    event_type="economic_calendar",
                    title=title,
                    event_time=next_time,
                    significance=significance,
                    source="calendar_template",
                    payload={"calendar_code": code},
                )
            )
    return events


def _next_weekday_time(reference: datetime, *, weekday: int, hour: int, minute: int) -> datetime:
    candidate_date = reference.date()
    days_ahead = (weekday - candidate_date.weekday()) % 7
    candidate_date = candidate_date + timedelta(days=days_ahead)
    candidate = datetime.combine(candidate_date, time(hour=hour, minute=minute, tzinfo=UTC))
    if candidate < reference:
        candidate = candidate + timedelta(days=7)
    return candidate


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
