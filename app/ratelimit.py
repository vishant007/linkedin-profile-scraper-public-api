"""Inbound rate limiting.

A token bucket per API key. Bursts are allowed up to the per-minute capacity,
then requests are refused until the bucket refills, which suits an API a person
explores interactively better than a hard fixed window would.

The limit is flat rather than weighted by the sections requested. That was
measured rather than assumed: LinkedIn returns the whole profile in one call, so
a request for one section costs exactly as much upstream as a request for all
five. A weighted limiter would model a cost that does not exist.

This protects the service and its callers from each other. The upstream session
is protected by the cache, which absorbs repeat requests for the same profile
before they ever reach LinkedIn.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field

from app.errors import RateLimited

MAX_TRACKED_KEYS = 1024


@dataclass
class _Bucket:
    tokens: float
    updated_at: float = field(default_factory=time.monotonic)


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self._capacity = float(per_minute)
        self._refill_per_second = per_minute / 60.0
        self._lock = threading.Lock()
        self._buckets: dict[str, _Bucket] = {}

    @property
    def enabled(self) -> bool:
        return self._capacity > 0

    def check(self, key: str) -> int:
        """Consume one token. Returns tokens remaining, or raises RateLimited."""
        if not self.enabled:
            return 0

        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                # Bound the map so an attacker cycling keys cannot grow it forever.
                if len(self._buckets) >= MAX_TRACKED_KEYS:
                    self._evict_stale(now)
                # updated_at must be the `now` captured above, not the creation
                # instant. Defaulting it makes elapsed negative on the first
                # call, docking a fraction of a token and refusing request one
                # whenever the capacity is small.
                bucket = _Bucket(tokens=self._capacity, updated_at=now)
                self._buckets[key] = bucket

            elapsed = now - bucket.updated_at
            bucket.tokens = min(
                self._capacity, bucket.tokens + elapsed * self._refill_per_second
            )
            bucket.updated_at = now

            if bucket.tokens < 1.0:
                deficit = 1.0 - bucket.tokens
                retry_after = max(1, math.ceil(deficit / self._refill_per_second))
                raise RateLimited(
                    f"Rate limit exceeded. Try again in {retry_after}s.",
                    retry_after=retry_after,
                )

            bucket.tokens -= 1.0
            # Refill is time-based, so tokens drift by fractions of a nanosecond.
            # Truncating 1.9999999 to 1 would under-report by a whole request.
            return max(0, int(bucket.tokens + 1e-6))

    def _evict_stale(self, now: float) -> None:
        """Drop buckets that have refilled completely; they carry no state."""
        full_after = self._capacity / self._refill_per_second
        for key in [k for k, b in self._buckets.items() if now - b.updated_at > full_after]:
            del self._buckets[key]
        if len(self._buckets) >= MAX_TRACKED_KEYS:  # still full: drop the oldest
            oldest = min(self._buckets, key=lambda k: self._buckets[k].updated_at)
            del self._buckets[oldest]

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


_limiter: RateLimiter | None = None


def get_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        from app.config import get_settings

        _limiter = RateLimiter(get_settings().rate_limit_per_minute)
    return _limiter


def reset_limiter() -> None:
    """Test hook."""
    global _limiter
    _limiter = None
