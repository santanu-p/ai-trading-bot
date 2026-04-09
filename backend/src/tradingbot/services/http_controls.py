from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int = 0
    remaining: int = 0


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = Lock()

    def consume(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        normalized_key = key.strip()
        if not normalized_key or limit <= 0 or window_seconds <= 0:
            return RateLimitResult(allowed=True, remaining=max(limit - 1, 0))

        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=window_seconds)

        with self._lock:
            bucket = self._events[normalized_key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                reset_at = bucket[0] + timedelta(seconds=window_seconds)
                retry_after = max(int((reset_at - now).total_seconds()) + 1, 1)
                return RateLimitResult(allowed=False, retry_after_seconds=retry_after, remaining=0)

            bucket.append(now)
            return RateLimitResult(
                allowed=True,
                remaining=max(limit - len(bucket), 0),
            )


_rate_limiter = SlidingWindowRateLimiter()


def rate_limiter() -> SlidingWindowRateLimiter:
    return _rate_limiter
