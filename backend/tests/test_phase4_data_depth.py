from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tradingbot.services.adapters import BarPoint, NewsItem
from tradingbot.services.data_quality import DataQualityPolicy, DataQualityValidator
from tradingbot.services.events import extract_structured_events, serialize_structured_events
from tradingbot.services.features import IndexContext, build_feature_snapshot, infer_market_index_context
from tradingbot.services.indicators import bar_summary


def _make_bars(
    *,
    start: datetime,
    count: int,
    interval_minutes: int,
    drift: float,
    base_price: float = 100.0,
) -> list[BarPoint]:
    rows: list[BarPoint] = []
    price = base_price
    for index in range(count):
        timestamp = start + timedelta(minutes=index * interval_minutes)
        open_price = price
        close_price = price + drift + (0.05 if index % 2 == 0 else -0.03)
        high_price = max(open_price, close_price) + 0.25
        low_price = min(open_price, close_price) - 0.2
        rows.append(
            BarPoint(
                timestamp=timestamp,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=1200 + (index * 35),
            )
        )
        price = close_price
    return rows


def test_phase4_bar_summary_exposes_richer_features() -> None:
    bars = _make_bars(
        start=datetime(2026, 4, 8, 13, 30, tzinfo=UTC),
        count=40,
        interval_minutes=5,
        drift=0.18,
    )
    summary = bar_summary(bars, interval_minutes=5)

    assert summary["intraday_volatility_pct"] > 0
    assert summary["gap_max_abs_pct"] >= summary["gap_mean_abs_pct"] >= 0
    assert summary["relative_volume_10"] > 0
    assert summary["atr_14"] > 0
    assert 0 <= summary["opening_range_position"] <= 1
    assert -1 <= summary["trend_alignment_score"] <= 1


def test_phase4_feature_snapshot_includes_index_context() -> None:
    start = datetime(2026, 4, 8, 13, 30, tzinfo=UTC)
    spy = _make_bars(start=start, count=40, interval_minutes=5, drift=0.22, base_price=500)
    qqq = _make_bars(start=start, count=40, interval_minutes=5, drift=0.16, base_price=430)
    context = infer_market_index_context({"SPY": spy, "QQQ": qqq})

    symbol_bars = _make_bars(start=start, count=40, interval_minutes=5, drift=0.2, base_price=210)
    snapshot = build_feature_snapshot(symbol_bars, interval_minutes=5, index_context=context)

    assert context.regime in {"risk_on", "mixed"}
    assert "spy_trend_pct" in snapshot
    assert "qqq_trend_pct" in snapshot
    assert "index_breadth_score" in snapshot
    assert "index_regime_score" in snapshot
    assert snapshot["index_regime_score"] >= 0


def test_phase4_structured_events_cover_news_and_calendar_context() -> None:
    now = datetime(2026, 4, 8, 12, 0, tzinfo=UTC)
    news = [
        NewsItem(
            headline="AAPL earnings scheduled after close as guidance rises",
            summary="The company highlighted stronger services momentum.",
            source="wire",
            created_at=now - timedelta(minutes=40),
            sentiment_hint="positive",
        ),
        NewsItem(
            headline="Broker upgrade lifts AAPL price target",
            summary="Analyst cites stronger demand and margin expansion.",
            source="wire",
            created_at=now - timedelta(minutes=30),
            sentiment_hint="positive",
        ),
        NewsItem(
            headline="CPI report cools while Fed commentary stays data dependent",
            summary="Macro release points to easing inflation pressure.",
            source="macro",
            created_at=now - timedelta(minutes=20),
            sentiment_hint="neutral",
        ),
    ]
    events = extract_structured_events(
        "AAPL",
        news,
        as_of=now,
        index_context=IndexContext(regime="risk_on"),
    )
    payload = serialize_structured_events(events)
    event_types = {item["event_type"] for item in payload}

    assert "earnings_date" in event_types
    assert "analyst_action" in event_types
    assert "macro_release" in event_types
    assert "sector_etf_context" in event_types
    assert "economic_calendar" in event_types


def test_phase4_data_quality_rejects_stale_and_gappy_feeds() -> None:
    now = datetime(2026, 4, 8, 11, 0, tzinfo=UTC)
    bars = [
        BarPoint(timestamp=datetime(2026, 4, 8, 9, 30, tzinfo=UTC), open=100, high=101, low=99.8, close=100.7, volume=1000),
        BarPoint(timestamp=datetime(2026, 4, 8, 9, 35, tzinfo=UTC), open=100.7, high=101.1, low=100.6, close=101.0, volume=1100),
        BarPoint(timestamp=datetime(2026, 4, 8, 9, 55, tzinfo=UTC), open=101.0, high=101.5, low=100.9, close=101.4, volume=900),
        BarPoint(timestamp=datetime(2026, 4, 8, 10, 0, tzinfo=UTC), open=101.4, high=101.7, low=101.2, close=101.6, volume=950),
    ]
    news = [
        NewsItem(
            headline="Old catalyst",
            summary="No new details.",
            source="wire",
            created_at=datetime(2026, 4, 8, 8, 0, tzinfo=UTC),
            sentiment_hint="neutral",
        )
    ]
    validator = DataQualityValidator(
        DataQualityPolicy(
            max_bar_staleness_minutes=15,
            max_news_staleness_minutes=20,
            max_missing_candle_ratio=0.1,
            abnormal_gap_multiplier=3.0,
        )
    )

    report = validator.evaluate(
        symbol="AAPL",
        bars=bars,
        news_items=news,
        interval_minutes=5,
        now=now,
        requires_timely_news=True,
    )
    codes = {issue.code for issue in report.issues}

    assert report.passed is False
    assert "stale_bars" in codes
    assert "missing_candles" in codes
    assert "abnormal_feed_gap" in codes
    assert "delayed_news_snapshot" in codes


def test_phase4_data_quality_accepts_fresh_complete_data() -> None:
    now = datetime(2026, 4, 8, 15, 5, tzinfo=UTC)
    bars = _make_bars(
        start=datetime(2026, 4, 8, 13, 30, tzinfo=UTC),
        count=20,
        interval_minutes=5,
        drift=0.14,
    )
    news = [
        NewsItem(
            headline="Fresh headline",
            summary="Timely catalyst update.",
            source="wire",
            created_at=now - timedelta(minutes=8),
            sentiment_hint="positive",
        )
    ]
    validator = DataQualityValidator(
        DataQualityPolicy(
            max_bar_staleness_minutes=20,
            max_news_staleness_minutes=60,
            max_missing_candle_ratio=0.2,
            abnormal_gap_multiplier=4.0,
        )
    )

    report = validator.evaluate(
        symbol="MSFT",
        bars=bars,
        news_items=news,
        interval_minutes=5,
        now=now,
        requires_timely_news=True,
    )

    assert report.passed is True
    assert all(issue.severity != "critical" for issue in report.issues)
