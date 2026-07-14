"""A tiny thread-safe TTL cache.

We wrap outbound Charity Commission calls with this so repeated lookups (the
same charity searched twice, a JSON view then a CSV export) don't re-hit the
public API. Financial data changes at most once a year, so a long TTL is safe.

Deliberately dependency-free and in-memory: it resets on restart, which is fine
for a single-process tool. The README notes how to swap in a persistent cache.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional


class TTLCache:
    def __init__(self, ttl_seconds: int = 86_400) -> None:
        self.ttl = ttl_seconds
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            value, expires_at = item
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (value, time.monotonic() + self.ttl)
