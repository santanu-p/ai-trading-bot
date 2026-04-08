from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from tradingbot.services.adapters import BarPoint, NewsItem


@dataclass(slots=True)
class DataQualityPolicy:
    max_bar_staleness_minutes: int = 20
    max_news_staleness_minutes: int = 120
    max_missing_candle_ratio: float = 0.12
    abnormal_gap_multiplier: float = 4.0


@dataclass(slots=True)
class DataQualityIssue:
    code: str
    message: str
    severity: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "payload": self.payload,
        }


@dataclass(slots=True)
class DataQualityReport:
    symbol: str
    checked_at: datetime
    issues: list[DataQualityIssue] = field(default_factory=list)
    data_timestamps: dict[str, str | None] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not any(issue.severity == "critical" for issue in self.issues)

    def rejection_notes(self) -> list[str]:
        return [issue.message for issue in self.issues if issue.severity == "critical"]

    def to_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "checked_at": self.checked_at.astimezone(UTC).isoformat(),
            "passed": self.passed,
            "issues": [issue.to_payload() for issue in self.issues],
            "data_timestamps": self.data_timestamps,
            "metrics": self.metrics,
        }


class DataQualityValidator:
    def __init__(self, policy: DataQualityPolicy | None = None) -> None:
        self.policy = policy or DataQualityPolicy()

    def evaluate(
        self,
        *,
        symbol: str,
        bars: list[BarPoint],
        news_items: list[NewsItem],
        interval_minutes: int,
        now: datetime,
        requires_timely_news: bool,
    ) -> DataQualityReport:
        normalized_now = _utc(now)
        ordered_bars = sorted(bars, key=lambda item: item.timestamp)
        ordered_news = sorted(news_items, key=lambda item: item.created_at)

        data_timestamps = {
            "checked_at": normalized_now.isoformat(),
            "first_bar_at": _iso_or_none(ordered_bars[0].timestamp if ordered_bars else None),
            "last_bar_at": _iso_or_none(ordered_bars[-1].timestamp if ordered_bars else None),
            "oldest_news_at": _iso_or_none(ordered_news[0].created_at if ordered_news else None),
            "latest_news_at": _iso_or_none(ordered_news[-1].created_at if ordered_news else None),
        }

        report = DataQualityReport(
            symbol=symbol,
            checked_at=normalized_now,
            data_timestamps=data_timestamps,
            metrics={
                "bars_count": float(len(ordered_bars)),
                "news_count": float(len(ordered_news)),
            },
        )

        if not ordered_bars:
            report.issues.append(
                DataQualityIssue(
                    code="no_bars",
                    message="No market bars were returned for the symbol.",
                    severity="critical",
                    payload={},
                )
            )
            return report

        last_bar_age = max((normalized_now - _utc(ordered_bars[-1].timestamp)).total_seconds() / 60, 0.0)
        report.metrics["last_bar_age_minutes"] = round(last_bar_age, 3)
        staleness_threshold = max(float(interval_minutes * 2), float(self.policy.max_bar_staleness_minutes))
        if last_bar_age > staleness_threshold:
            report.issues.append(
                DataQualityIssue(
                    code="stale_bars",
                    message="Bar feed appears stale for this symbol.",
                    severity="critical",
                    payload={
                        "last_bar_age_minutes": round(last_bar_age, 3),
                        "threshold_minutes": round(staleness_threshold, 3),
                    },
                )
            )

        expected_intervals = int(
            max((_utc(ordered_bars[-1].timestamp) - _utc(ordered_bars[0].timestamp)).total_seconds(), 0)
            // max(interval_minutes * 60, 1)
        )
        observed_intervals = max(len(ordered_bars) - 1, 0)
        missing_candles = max(expected_intervals - observed_intervals, 0)
        missing_ratio = (missing_candles / max(expected_intervals, 1)) if expected_intervals > 0 else 0.0
        report.metrics["missing_candles"] = float(missing_candles)
        report.metrics["missing_candle_ratio"] = round(missing_ratio, 4)
        if expected_intervals > 0 and missing_ratio > self.policy.max_missing_candle_ratio:
            report.issues.append(
                DataQualityIssue(
                    code="missing_candles",
                    message="Detected missing candles in the bar feed window.",
                    severity="critical",
                    payload={
                        "expected_intervals": expected_intervals,
                        "observed_intervals": observed_intervals,
                        "missing_candles": missing_candles,
                        "missing_ratio": round(missing_ratio, 4),
                    },
                )
            )

        largest_gap = _largest_gap_minutes(ordered_bars)
        report.metrics["largest_feed_gap_minutes"] = round(largest_gap, 3)
        if largest_gap > (interval_minutes * self.policy.abnormal_gap_multiplier):
            report.issues.append(
                DataQualityIssue(
                    code="abnormal_feed_gap",
                    message="Detected abnormal spacing between consecutive candles.",
                    severity="critical",
                    payload={
                        "largest_gap_minutes": round(largest_gap, 3),
                        "expected_interval_minutes": interval_minutes,
                    },
                )
            )

        if requires_timely_news:
            if ordered_news:
                news_age = max((normalized_now - _utc(ordered_news[-1].created_at)).total_seconds() / 60, 0.0)
                report.metrics["latest_news_age_minutes"] = round(news_age, 3)
                if news_age > float(self.policy.max_news_staleness_minutes):
                    report.issues.append(
                        DataQualityIssue(
                            code="delayed_news_snapshot",
                            message="Latest news snapshot is too old for timely decisioning.",
                            severity="critical",
                            payload={
                                "latest_news_age_minutes": round(news_age, 3),
                                "threshold_minutes": float(self.policy.max_news_staleness_minutes),
                            },
                        )
                    )
            else:
                report.issues.append(
                    DataQualityIssue(
                        code="news_snapshot_empty",
                        message="No recent news items were available for this scan.",
                        severity="warning",
                        payload={},
                    )
                )

        return report


def _largest_gap_minutes(bars: list[BarPoint]) -> float:
    if len(bars) < 2:
        return 0.0
    gaps = [
        (_utc(current.timestamp) - _utc(previous.timestamp)).total_seconds() / 60
        for previous, current in zip(bars[:-1], bars[1:], strict=True)
    ]
    return max(gaps, default=0.0)


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _utc(value).isoformat()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
