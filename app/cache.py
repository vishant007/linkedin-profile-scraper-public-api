"""Profile cache.

Doing double duty. The obvious job is latency: a repeat request is answered from
memory instead of crossing the network. The job that actually matters here is
protecting the upstream session -- ten clicks on "Try it out" become one call to
LinkedIn instead of ten, and a burst from a single account is precisely the
pattern that gets one flagged.

It also degrades gracefully: if the session dies, profiles already fetched keep
being served until their entries expire.

The key includes `auth_id`. Today every handle resolves to the same session so
it changes nothing, but LinkedIn discloses different amounts of a profile
depending on the viewing account -- so the moment this became multi-tenant, a
key without it would serve one caller's view to another. Cheaper to be correct
now than to remember later.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from app.schemas import Profile, ProfileWarning, Section

MAX_ENTRIES = 512  # bounded so a long-running process cannot grow without limit


@dataclass(frozen=True)
class CachedProfile:
    profile: Profile
    warnings: list[ProfileWarning]
    fetched_at: datetime  # when LinkedIn was actually called, not when served
    stored_at: float


class ProfileCache:
    def __init__(self, ttl_seconds: int, max_entries: int = MAX_ENTRIES) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple, CachedProfile] = OrderedDict()

    @staticmethod
    def key(auth_id: str, public_id: str, sections: Iterable[Section]) -> tuple:
        # Sections are part of the key because they change the response shape.
        return (auth_id, public_id.lower(), tuple(sorted(s.value for s in sections)))

    def get(self, key: tuple) -> CachedProfile | None:
        if self._ttl <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if now - entry.stored_at > self._ttl:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)  # keep hot entries alive under LRU
            return entry

    def put(
        self,
        key: tuple,
        profile: Profile,
        warnings: list[ProfileWarning],
        fetched_at: datetime,
    ) -> None:
        if self._ttl <= 0:
            return
        with self._lock:
            self._entries[key] = CachedProfile(
                profile=profile,
                warnings=warnings,
                fetched_at=fetched_at,
                stored_at=time.monotonic(),
            )
            self._entries.move_to_end(key)
            while len(self._entries) > self._max:
                self._entries.popitem(last=False)  # evict least recently used

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


_cache: ProfileCache | None = None


def get_cache() -> ProfileCache:
    global _cache
    if _cache is None:
        from app.config import get_settings

        _cache = ProfileCache(get_settings().cache_ttl_seconds)
    return _cache


def reset_cache() -> None:
    """Test hook."""
    global _cache
    _cache = None
