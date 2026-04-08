from __future__ import annotations

from statistics import mean, pstdev

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


def average_true_range(bars: list[BarPoint], window: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    true_ranges: list[float] = []
    for previous, current in zip(bars[:-1], bars[1:], strict=True):
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    sample = true_ranges[-window:] if len(true_ranges) >= window else true_ranges
    return mean(sample) if sample else 0.0


def intraday_volatility_pct(closes: list[float], window: int = 20) -> float:
    if len(closes) < 2:
        return 0.0
    returns = [
        (current - previous) / max(previous, 1e-6)
        for previous, current in zip(closes[:-1], closes[1:], strict=True)
    ]
    sample = returns[-window:] if len(returns) >= window else returns
    return pstdev(sample) * 100 if len(sample) >= 2 else 0.0


def gap_statistics(bars: list[BarPoint]) -> tuple[float, float, float]:
    if len(bars) < 2:
        return 0.0, 0.0, 0.0
    gaps = [
        ((current.open - previous.close) / max(previous.close, 1e-6)) * 100
        for previous, current in zip(bars[:-1], bars[1:], strict=True)
    ]
    latest = gaps[-1]
    abs_gaps = [abs(item) for item in gaps]
    return latest, mean(abs_gaps), max(abs_gaps)


def relative_volume(volumes: list[float], window: int = 10) -> float:
    if not volumes:
        return 0.0
    if len(volumes) == 1:
        return 1.0 if volumes[0] > 0 else 0.0
    lookback = volumes[-(window + 1) : -1]
    baseline = mean(lookback) if lookback else mean(volumes[:-1])
    if baseline <= 0:
        return 0.0
    return volumes[-1] / baseline


def opening_range_metrics(bars: list[BarPoint], interval_minutes: int | None = None) -> tuple[float, float, float]:
    if not bars:
        return 0.0, 0.5, 0.0
    if interval_minutes is not None and interval_minutes > 0:
        opening_bars = max(2, int(round(30 / interval_minutes)))
    else:
        opening_bars = 6
    opening_slice = bars[: min(len(bars), opening_bars)]
    opening_high = max(item.high for item in opening_slice)
    opening_low = min(item.low for item in opening_slice)
    first_open = opening_slice[0].open
    last_close = bars[-1].close
    width_pct = ((opening_high - opening_low) / max(first_open, 1e-6)) * 100
    if opening_high > opening_low:
        position = (last_close - opening_low) / (opening_high - opening_low)
    else:
        position = 0.5
    clamped_position = max(0.0, min(position, 1.0))
    if last_close > opening_high:
        breakout_pct = ((last_close - opening_high) / max(opening_high, 1e-6)) * 100
    elif last_close < opening_low:
        breakout_pct = ((last_close - opening_low) / max(opening_low, 1e-6)) * 100
    else:
        breakout_pct = 0.0
    return width_pct, clamped_position, breakout_pct


def trend_alignment_score(closes: list[float]) -> float:
    if not closes:
        return 0.0
    windows = ((5, 10), (10, 20), (20, 40))
    score = 0
    for fast_window, slow_window in windows:
        fast = simple_moving_average(closes, fast_window)
        slow = simple_moving_average(closes, slow_window)
        if fast > slow:
            score += 1
        elif fast < slow:
            score -= 1
    return score / len(windows)


def _default_summary() -> dict[str, float]:
    return {
        "last_close": 0.0,
        "sma_10": 0.0,
        "sma_20": 0.0,
        "rsi_14": 50.0,
        "avg_volume": 0.0,
        "momentum_pct": 0.0,
        "intraday_volatility_pct": 0.0,
        "gap_latest_pct": 0.0,
        "gap_mean_abs_pct": 0.0,
        "gap_max_abs_pct": 0.0,
        "relative_volume_10": 0.0,
        "atr_14": 0.0,
        "atr_stop_distance_pct": 0.0,
        "opening_range_width_pct": 0.0,
        "opening_range_position": 0.5,
        "opening_range_breakout_pct": 0.0,
        "trend_alignment_score": 0.0,
    }


def bar_summary(bars: list[BarPoint], *, interval_minutes: int | None = None) -> dict[str, float]:
    closes = [bar.close for bar in bars]
    volumes = [bar.volume for bar in bars]
    if not closes:
        return _default_summary()
    first_close = closes[0]
    last_close = closes[-1]
    atr_14 = average_true_range(bars, window=14)
    gap_latest, gap_mean_abs, gap_max_abs = gap_statistics(bars)
    opening_width, opening_position, opening_breakout = opening_range_metrics(
        bars,
        interval_minutes=interval_minutes,
    )
    return {
        "last_close": last_close,
        "sma_10": round(simple_moving_average(closes, 10), 2),
        "sma_20": round(simple_moving_average(closes, 20), 2),
        "rsi_14": relative_strength(closes, 14),
        "avg_volume": round(simple_moving_average(volumes, min(len(volumes), 10)), 2),
        "momentum_pct": round(((last_close - first_close) / max(first_close, 0.01)) * 100, 2),
        "intraday_volatility_pct": round(intraday_volatility_pct(closes, window=20), 4),
        "gap_latest_pct": round(gap_latest, 4),
        "gap_mean_abs_pct": round(gap_mean_abs, 4),
        "gap_max_abs_pct": round(gap_max_abs, 4),
        "relative_volume_10": round(relative_volume(volumes, window=10), 4),
        "atr_14": round(atr_14, 4),
        "atr_stop_distance_pct": round((atr_14 / max(last_close, 1e-6)) * 100, 4),
        "opening_range_width_pct": round(opening_width, 4),
        "opening_range_position": round(opening_position, 4),
        "opening_range_breakout_pct": round(opening_breakout, 4),
        "trend_alignment_score": round(trend_alignment_score(closes), 4),
    }
