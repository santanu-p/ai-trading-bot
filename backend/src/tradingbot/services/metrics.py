from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any


@dataclass(frozen=True, slots=True)
class _MetricEvent:
    kind: str
    name: str
    value: float
    tags: tuple[tuple[str, str], ...]
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class CounterMetricSnapshot:
    name: str
    value: float
    tags: dict[str, str]


@dataclass(frozen=True, slots=True)
class DurationMetricSnapshot:
    name: str
    samples: int
    avg_ms: float
    p95_ms: float
    max_ms: float
    tags: dict[str, str]


class MetricsRegistry:
    def __init__(self, *, max_events: int = 20_000) -> None:
        self._events: deque[_MetricEvent] = deque(maxlen=max_events)
        self._lock = Lock()

    def record_counter(self, name: str, *, value: float = 1.0, tags: dict[str, Any] | None = None) -> None:
        self._record("counter", name, value, tags)

    def record_duration_ms(self, name: str, *, duration_ms: float, tags: dict[str, Any] | None = None) -> None:
        self._record("duration_ms", name, max(duration_ms, 0.0), tags)

    def summarize(
        self,
        *,
        window_minutes: int = 60,
    ) -> tuple[list[CounterMetricSnapshot], list[DurationMetricSnapshot]]:
        window = max(window_minutes, 1)
        cutoff = datetime.now(UTC) - timedelta(minutes=window)

        with self._lock:
            events = [event for event in self._events if event.observed_at >= cutoff]

        counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        durations: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = defaultdict(list)

        for event in events:
            key = (event.name, event.tags)
            if event.kind == "counter":
                counters[key] += event.value
            elif event.kind == "duration_ms":
                durations[key].append(event.value)

        counter_rows = [
            CounterMetricSnapshot(
                name=name,
                value=round(value, 6),
                tags=dict(tags),
            )
            for (name, tags), value in counters.items()
        ]
        counter_rows.sort(key=lambda row: (row.name, tuple(sorted(row.tags.items()))))

        duration_rows: list[DurationMetricSnapshot] = []
        for (name, tags), values in durations.items():
            ordered = sorted(values)
            sample_count = len(ordered)
            if sample_count == 0:
                continue
            p95_index = max(int(sample_count * 0.95) - 1, 0)
            duration_rows.append(
                DurationMetricSnapshot(
                    name=name,
                    samples=sample_count,
                    avg_ms=round(sum(ordered) / sample_count, 3),
                    p95_ms=round(ordered[p95_index], 3),
                    max_ms=round(ordered[-1], 3),
                    tags=dict(tags),
                )
            )
        duration_rows.sort(key=lambda row: (row.name, tuple(sorted(row.tags.items()))))
        return counter_rows, duration_rows

    def _record(self, kind: str, name: str, value: float, tags: dict[str, Any] | None) -> None:
        normalized_name = name.strip().lower().replace(" ", "_")
        if not normalized_name:
            return
        normalized_tags = _normalize_tags(tags)
        event = _MetricEvent(
            kind=kind,
            name=normalized_name,
            value=float(value),
            tags=normalized_tags,
            observed_at=datetime.now(UTC),
        )
        with self._lock:
            self._events.append(event)


def _normalize_tags(tags: dict[str, Any] | None) -> tuple[tuple[str, str], ...]:
    if not tags:
        return ()
    normalized: list[tuple[str, str]] = []
    for key, value in tags.items():
        key_text = str(key).strip().lower().replace(" ", "_")
        if not key_text:
            continue
        value_text = str(value).strip()
        if not value_text:
            continue
        normalized.append((key_text, value_text))
    normalized.sort(key=lambda item: item[0])
    return tuple(normalized)


_registry = MetricsRegistry()


def metrics_registry() -> MetricsRegistry:
    return _registry


def observe_counter(name: str, *, value: float = 1.0, tags: dict[str, Any] | None = None) -> None:
    _registry.record_counter(name, value=value, tags=tags)


def observe_duration_ms(name: str, *, duration_ms: float, tags: dict[str, Any] | None = None) -> None:
    _registry.record_duration_ms(name, duration_ms=duration_ms, tags=tags)
