"""Shared utility functions used across the trading bot backend."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def safe_float(value: Any, *, fallback: float = 0.0) -> float:
    """Safely convert a value to float, returning fallback on failure."""
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def safe_float_optional(value: Any, *, fallback: float | None = None) -> float | None:
    """Safely convert a value to float, returning None on failure."""
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def safe_str(value: Any) -> str | None:
    """Safely convert a value to a stripped string, returning None if empty."""
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def to_datetime(value: Any) -> datetime | None:
    """Parse a datetime from various input formats (ISO 8601 strings, datetime objects)."""
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
