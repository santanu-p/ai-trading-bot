"""LLM cost tracking and intelligent scan scheduling.

Provides:
- Token usage and cost estimation per LLM call
- Aggregated cost reporting by provider, model, and time period
- Intelligent scan scheduling (skip low-opportunity periods)
- Data caching for stable context (sector, calendar)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any

from tradingbot.services.metrics import observe_counter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cost models (per-token pricing in USD)
# ---------------------------------------------------------------------------
_MODEL_PRICING: dict[str, dict[str, float]] = {
    # OpenAI models
    "gpt-4o": {"input_per_1k": 0.0025, "output_per_1k": 0.01},
    "gpt-4o-mini": {"input_per_1k": 0.00015, "output_per_1k": 0.0006},
    "gpt-4-turbo": {"input_per_1k": 0.01, "output_per_1k": 0.03},
    "gpt-4": {"input_per_1k": 0.03, "output_per_1k": 0.06},
    "gpt-3.5-turbo": {"input_per_1k": 0.0005, "output_per_1k": 0.0015},
    "o4-mini": {"input_per_1k": 0.0011, "output_per_1k": 0.0044},
    # Gemini models
    "gemini-2.0-flash": {"input_per_1k": 0.0, "output_per_1k": 0.0},  # Free tier
    "gemini-1.5-flash": {"input_per_1k": 0.000075, "output_per_1k": 0.0003},
    "gemini-1.5-pro": {"input_per_1k": 0.00125, "output_per_1k": 0.005},
    "gemini-2.5-flash": {"input_per_1k": 0.00015, "output_per_1k": 0.0035},
    "gemini-2.5-pro": {"input_per_1k": 0.00125, "output_per_1k": 0.01},
}


# ---------------------------------------------------------------------------
# Cost record
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class LLMCallRecord:
    """Record of a single LLM API call with cost estimation."""

    call_id: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    operation: str  # e.g., "market_scan", "committee_vote"
    symbol: str | None
    profile_id: int | None
    latency_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    cached: bool = False


# ---------------------------------------------------------------------------
# Cost tracker (in-process)
# ---------------------------------------------------------------------------
_cost_lock = Lock()
_cost_records: list[LLMCallRecord] = []
_MAX_RECORDS = 10_000


def record_llm_call(
    *,
    call_id: str,
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    operation: str = "unknown",
    symbol: str | None = None,
    profile_id: int | None = None,
    latency_ms: float = 0.0,
    cached: bool = False,
) -> LLMCallRecord:
    """Record an LLM API call with cost estimation."""
    pricing = _MODEL_PRICING.get(model, {"input_per_1k": 0.001, "output_per_1k": 0.002})
    cost = (input_tokens / 1000.0) * pricing["input_per_1k"] + (output_tokens / 1000.0) * pricing["output_per_1k"]

    record = LLMCallRecord(
        call_id=call_id,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=round(cost, 6),
        operation=operation,
        symbol=symbol,
        profile_id=profile_id,
        latency_ms=latency_ms,
        cached=cached,
    )

    with _cost_lock:
        _cost_records.append(record)
        if len(_cost_records) > _MAX_RECORDS:
            del _cost_records[: len(_cost_records) - _MAX_RECORDS]

    observe_counter(
        "llm.cost_usd",
        value=cost,
        tags={"provider": provider, "model": model, "operation": operation},
    )
    observe_counter(
        "llm.tokens",
        value=float(input_tokens + output_tokens),
        tags={"provider": provider, "model": model, "direction": "total"},
    )

    return record


def get_cost_summary(
    *,
    window_minutes: int = 1440,  # Default: 24 hours
    profile_id: int | None = None,
) -> dict[str, Any]:
    """Generate a cost summary for the given time window."""
    cutoff = datetime.now(UTC) - timedelta(minutes=window_minutes)

    with _cost_lock:
        filtered = [
            r for r in _cost_records
            if r.timestamp >= cutoff
            and (profile_id is None or r.profile_id == profile_id)
        ]

    if not filtered:
        return {
            "window_minutes": window_minutes,
            "total_calls": 0,
            "total_cost_usd": 0.0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "by_provider": {},
            "by_model": {},
            "by_operation": {},
        }

    total_cost = sum(r.estimated_cost_usd for r in filtered)
    total_input = sum(r.input_tokens for r in filtered)
    total_output = sum(r.output_tokens for r in filtered)

    by_provider: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "cost": 0.0, "tokens": 0})
    by_model: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "cost": 0.0, "tokens": 0})
    by_operation: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "cost": 0.0, "tokens": 0})

    for r in filtered:
        by_provider[r.provider]["calls"] += 1
        by_provider[r.provider]["cost"] += r.estimated_cost_usd
        by_provider[r.provider]["tokens"] += r.input_tokens + r.output_tokens

        by_model[r.model]["calls"] += 1
        by_model[r.model]["cost"] += r.estimated_cost_usd
        by_model[r.model]["tokens"] += r.input_tokens + r.output_tokens

        by_operation[r.operation]["calls"] += 1
        by_operation[r.operation]["cost"] += r.estimated_cost_usd
        by_operation[r.operation]["tokens"] += r.input_tokens + r.output_tokens

    def _round_dict(d: dict) -> dict:
        return {k: round(v, 6) if isinstance(v, float) else v for k, v in d.items()}

    return {
        "window_minutes": window_minutes,
        "total_calls": len(filtered),
        "total_cost_usd": round(total_cost, 6),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "cached_calls": sum(1 for r in filtered if r.cached),
        "avg_latency_ms": round(sum(r.latency_ms for r in filtered) / len(filtered), 2),
        "by_provider": {k: _round_dict(dict(v)) for k, v in by_provider.items()},
        "by_model": {k: _round_dict(dict(v)) for k, v in by_model.items()},
        "by_operation": {k: _round_dict(dict(v)) for k, v in by_operation.items()},
    }


# ---------------------------------------------------------------------------
# Intelligent scan scheduling
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class ScanOpportunityScore:
    """Assessment of whether a scan is worth running right now."""

    should_scan: bool
    score: float  # 0.0 (skip) to 1.0 (definitely scan)
    reason: str
    factors: dict[str, float] = field(default_factory=dict)


def assess_scan_opportunity(
    *,
    market_open: bool = True,
    minutes_since_open: int = 0,
    minutes_until_close: int = 390,
    recent_scan_minutes_ago: int | None = None,
    scan_interval_minutes: int = 15,
    volatility_score: float = 0.5,
    volume_score: float = 0.5,
) -> ScanOpportunityScore:
    """Determine if a market scan is worth running right now.

    Considers:
    - Market hours (skip pre/post market unless configured)
    - Time since last scan (avoid redundant scans)
    - Market volatility (scan more during high-vol periods)
    - Volume profile (skip low-volume lunchtime dip)
    """
    factors: dict[str, float] = {}
    scores: list[float] = []

    # Market hours factor
    if not market_open:
        return ScanOpportunityScore(
            should_scan=False,
            score=0.0,
            reason="Market is closed.",
            factors={"market_open": 0.0},
        )
    factors["market_open"] = 1.0

    # Time-of-day factor (opening/closing hours are highest opportunity)
    if minutes_since_open <= 30:
        tod_score = 1.0  # Opening range — always scan
    elif minutes_until_close <= 30:
        tod_score = 0.9  # Closing range — important
    elif 90 <= minutes_since_open <= 180:
        tod_score = 0.4  # Lunchtime dip — low opportunity
    else:
        tod_score = 0.6  # Normal hours
    factors["time_of_day"] = tod_score
    scores.append(tod_score)

    # Recency factor
    if recent_scan_minutes_ago is not None:
        if recent_scan_minutes_ago < scan_interval_minutes * 0.5:
            recency_score = 0.1  # Too recent
        elif recent_scan_minutes_ago < scan_interval_minutes:
            recency_score = 0.5
        else:
            recency_score = 1.0
    else:
        recency_score = 1.0  # No recent scan — definitely scan
    factors["recency"] = recency_score
    scores.append(recency_score)

    # Volatility factor (scan more during high vol)
    vol_score = min(volatility_score * 1.5, 1.0)  # Amplify vol signal
    factors["volatility"] = vol_score
    scores.append(vol_score)

    # Volume factor
    factors["volume"] = volume_score
    scores.append(volume_score)

    # Weighted average
    weights = [0.25, 0.25, 0.3, 0.2]  # tod, recency, vol, volume
    final_score = sum(s * w for s, w in zip(scores, weights))

    threshold = 0.35
    should_scan = final_score >= threshold
    reason = "Score above threshold." if should_scan else f"Score {final_score:.2f} below threshold {threshold}."

    return ScanOpportunityScore(
        should_scan=should_scan,
        score=round(final_score, 4),
        reason=reason,
        factors=factors,
    )


# ---------------------------------------------------------------------------
# Data caching for stable context
# ---------------------------------------------------------------------------
_data_cache: dict[str, tuple[Any, datetime]] = {}
_data_cache_lock = Lock()


def get_cached_data(key: str, *, ttl_minutes: int = 60) -> Any | None:
    """Get data from cache if it exists and hasn't expired."""
    with _data_cache_lock:
        entry = _data_cache.get(key)
        if entry is None:
            return None
        value, stored_at = entry
        if (datetime.now(UTC) - stored_at) > timedelta(minutes=ttl_minutes):
            del _data_cache[key]
            return None
        observe_counter("cache.hit", tags={"key": key})
        return value


def set_cached_data(key: str, value: Any) -> None:
    """Store data in the cache."""
    with _data_cache_lock:
        _data_cache[key] = (value, datetime.now(UTC))
    observe_counter("cache.set", tags={"key": key})


def clear_cache() -> None:
    """Clear all cached data."""
    with _data_cache_lock:
        _data_cache.clear()
