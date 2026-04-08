from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping

from tradingbot.services.adapters import BarPoint
from tradingbot.services.indicators import bar_summary


@dataclass(slots=True)
class IndexContext:
    spy_trend_pct: float = 0.0
    qqq_trend_pct: float = 0.0
    breadth_score: float = 0.5
    regime: str = "neutral"
    as_of: datetime | None = None

    @property
    def regime_score(self) -> float:
        if self.regime == "risk_on":
            return 1.0
        if self.regime == "risk_off":
            return -1.0
        return 0.0

    def to_payload(self) -> dict[str, object]:
        return {
            "spy_trend_pct": round(self.spy_trend_pct, 4),
            "qqq_trend_pct": round(self.qqq_trend_pct, 4),
            "breadth_score": round(self.breadth_score, 4),
            "regime": self.regime,
            "as_of": self.as_of.astimezone(UTC).isoformat() if self.as_of else None,
            "regime_score": self.regime_score,
        }


def infer_market_index_context(index_bars: Mapping[str, list[BarPoint]]) -> IndexContext:
    spy = _sorted_bars(index_bars.get("SPY", []))
    qqq = _sorted_bars(index_bars.get("QQQ", []))
    spy_summary = bar_summary(spy)
    qqq_summary = bar_summary(qqq)

    spy_trend = _trend_pct(spy)
    qqq_trend = _trend_pct(qqq)
    breadth_signals: list[float] = []
    if spy:
        breadth_signals.append(1.0 if spy_summary["last_close"] >= spy_summary["sma_20"] else 0.0)
        breadth_signals.append(1.0 if spy_summary["momentum_pct"] >= 0 else 0.0)
    if qqq:
        breadth_signals.append(1.0 if qqq_summary["last_close"] >= qqq_summary["sma_20"] else 0.0)
        breadth_signals.append(1.0 if qqq_summary["momentum_pct"] >= 0 else 0.0)
    breadth_score = sum(breadth_signals) / len(breadth_signals) if breadth_signals else 0.5

    if spy and qqq and spy_trend > 0.1 and qqq_trend > 0.1 and breadth_score >= 0.6:
        regime = "risk_on"
    elif spy and qqq and spy_trend < -0.1 and qqq_trend < -0.1 and breadth_score <= 0.4:
        regime = "risk_off"
    elif spy or qqq:
        regime = "mixed"
    else:
        regime = "neutral"

    as_of = max(
        [bars[-1].timestamp for bars in (spy, qqq) if bars],
        default=None,
    )
    return IndexContext(
        spy_trend_pct=spy_trend,
        qqq_trend_pct=qqq_trend,
        breadth_score=breadth_score,
        regime=regime,
        as_of=as_of,
    )


def build_feature_snapshot(
    bars: list[BarPoint],
    *,
    interval_minutes: int,
    index_context: IndexContext | None = None,
) -> dict[str, float]:
    base = bar_summary(bars, interval_minutes=interval_minutes)
    context = index_context or IndexContext()
    base.update(
        {
            "spy_trend_pct": round(context.spy_trend_pct, 4),
            "qqq_trend_pct": round(context.qqq_trend_pct, 4),
            "index_breadth_score": round(context.breadth_score, 4),
            "index_regime_score": round(context.regime_score, 4),
        }
    )
    return base


def _sorted_bars(bars: list[BarPoint]) -> list[BarPoint]:
    return sorted(bars, key=lambda row: row.timestamp)


def _trend_pct(bars: list[BarPoint]) -> float:
    if len(bars) < 2:
        return 0.0
    lookback = bars[-20:] if len(bars) >= 20 else bars
    first_close = lookback[0].close
    last_close = lookback[-1].close
    return ((last_close - first_close) / max(first_close, 1e-6)) * 100
