from __future__ import annotations

from statistics import mean

from tradingbot.services.adapters import BarPoint


def simple_moving_average(values: list[float], window: int) -> float:
    if not values:
        return 0.0
    if len(values) < window:
        return mean(values)
    return mean(values[-window:])


def relative_strength(values: list[float], window: int = 14) -> float:
    if len(values) < 2:
        return 50.0
    deltas = [current - previous for previous, current in zip(values[:-1], values[1:], strict=True)]
    gains = [delta for delta in deltas[-window:] if delta > 0]
    losses = [abs(delta) for delta in deltas[-window:] if delta < 0]
    average_gain = sum(gains) / max(len(gains), 1)
    average_loss = sum(losses) / max(len(losses), 1)
    if average_loss == 0:
        return 100.0
    rs = average_gain / average_loss
    return round(100 - (100 / (1 + rs)), 2)


def bar_summary(bars: list[BarPoint]) -> dict[str, float]:
    closes = [bar.close for bar in bars]
    volumes = [bar.volume for bar in bars]
    if not closes:
        return {
            "last_close": 0.0,
            "sma_10": 0.0,
            "sma_20": 0.0,
            "rsi_14": 50.0,
            "avg_volume": 0.0,
            "momentum_pct": 0.0,
        }
    first_close = closes[0]
    last_close = closes[-1]
    return {
        "last_close": last_close,
        "sma_10": round(simple_moving_average(closes, 10), 2),
        "sma_20": round(simple_moving_average(closes, 20), 2),
        "rsi_14": relative_strength(closes, 14),
        "avg_volume": round(simple_moving_average(volumes, min(len(volumes), 10)), 2),
        "momentum_pct": round(((last_close - first_close) / max(first_close, 0.01)) * 100, 2),
    }

