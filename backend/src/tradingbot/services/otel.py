"""Lightweight distributed tracing context using contextvars.

Provides trace_id / span_id propagation across API → worker → broker calls
without requiring the full OpenTelemetry SDK.  When an external OTel collector
is available, these IDs can be forwarded via the W3C Trace-Context header.
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Generator
from uuid import uuid4

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context variables
# ---------------------------------------------------------------------------
_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
_span_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("span_id", default=None)
_parent_span_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("parent_span_id", default=None)


def current_trace_id() -> str | None:
    return _trace_id_var.get()


def current_span_id() -> str | None:
    return _span_id_var.get()


def current_parent_span_id() -> str | None:
    return _parent_span_var.get()


# ---------------------------------------------------------------------------
# Span data
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class SpanRecord:
    """Lightweight representation of a finished span for export."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    operation: str
    service: str
    started_at: datetime
    finished_at: datetime
    duration_ms: float
    status: str  # "ok" | "error"
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Span collector (in-process ring buffer, replaced by external exporter later)
# ---------------------------------------------------------------------------
_MAX_SPANS = 5_000
_span_buffer: list[SpanRecord] = []


def _record_span(span: SpanRecord) -> None:
    _span_buffer.append(span)
    if len(_span_buffer) > _MAX_SPANS:
        del _span_buffer[: len(_span_buffer) - _MAX_SPANS]


def drain_spans(limit: int = 500) -> list[SpanRecord]:
    """Return and clear up to *limit* collected spans."""
    batch = _span_buffer[:limit]
    del _span_buffer[:limit]
    return batch


def recent_spans(limit: int = 100) -> list[SpanRecord]:
    """Peek at recent spans without draining."""
    return list(_span_buffer[-limit:])


# ---------------------------------------------------------------------------
# Context managers
# ---------------------------------------------------------------------------
def _generate_id() -> str:
    return uuid4().hex[:16]


@contextmanager
def trace_context(
    *,
    operation: str,
    service: str = "tradingbot",
    trace_id: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Generator[str, None, None]:
    """Start a new trace (root span).  Yields the trace_id.

    Use this at the outermost boundary (API request handler, Celery task).
    """
    resolved_trace_id = trace_id or _generate_id()
    span_id = _generate_id()

    trace_token = _trace_id_var.set(resolved_trace_id)
    span_token = _span_id_var.set(span_id)
    parent_token = _parent_span_var.set(None)

    started_at = datetime.now(UTC)
    started = perf_counter()
    status = "ok"
    span_events: list[dict[str, Any]] = []
    try:
        yield resolved_trace_id
    except Exception:
        status = "error"
        raise
    finally:
        duration_ms = (perf_counter() - started) * 1000
        _record_span(
            SpanRecord(
                trace_id=resolved_trace_id,
                span_id=span_id,
                parent_span_id=None,
                operation=operation,
                service=service,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                duration_ms=round(duration_ms, 3),
                status=status,
                attributes=dict(attributes or {}),
                events=span_events,
            )
        )
        _trace_id_var.reset(trace_token)
        _span_id_var.reset(span_token)
        _parent_span_var.reset(parent_token)


@contextmanager
def child_span(
    *,
    operation: str,
    service: str = "tradingbot",
    attributes: dict[str, Any] | None = None,
) -> Generator[str, None, None]:
    """Start a child span within an existing trace.  Yields the span_id."""
    parent_trace_id = _trace_id_var.get()
    parent_span_id = _span_id_var.get()
    span_id = _generate_id()

    span_token = _span_id_var.set(span_id)
    parent_token = _parent_span_var.set(parent_span_id)

    started_at = datetime.now(UTC)
    started = perf_counter()
    status = "ok"
    try:
        yield span_id
    except Exception:
        status = "error"
        raise
    finally:
        duration_ms = (perf_counter() - started) * 1000
        _record_span(
            SpanRecord(
                trace_id=parent_trace_id or _generate_id(),
                span_id=span_id,
                parent_span_id=parent_span_id,
                operation=operation,
                service=service,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                duration_ms=round(duration_ms, 3),
                status=status,
                attributes=dict(attributes or {}),
                events=[],
            )
        )
        _span_id_var.reset(span_token)
        _parent_span_var.reset(parent_token)


# ---------------------------------------------------------------------------
# W3C Trace-Context header helpers
# ---------------------------------------------------------------------------
def traceparent_header() -> str | None:
    """Build a W3C traceparent header from current context, or None."""
    trace_id = _trace_id_var.get()
    span_id = _span_id_var.get()
    if not trace_id or not span_id:
        return None
    padded_trace = trace_id.ljust(32, "0")[:32]
    padded_span = span_id.ljust(16, "0")[:16]
    return f"00-{padded_trace}-{padded_span}-01"


def parse_traceparent(header: str) -> tuple[str | None, str | None]:
    """Parse a W3C traceparent header into (trace_id, parent_span_id)."""
    parts = header.strip().split("-")
    if len(parts) < 4:
        return None, None
    return parts[1], parts[2]
