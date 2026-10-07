import threading
import time
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from starlette.status import HTTP_409_CONFLICT

from app.core.cache.protocol import CacheStatus
from app.core.utils import Singleton


class SyncIdempotencyCache(metaclass=Singleton):
    """Thread-safe TTL cache that runs a function at most once per key.

    For sync code such as `def` endpoints, which share the threadpool. Expired
    entries are dropped on lookup; the owner calls evict_expired() periodically,
    for example from a daemon thread started in the lifespan, to free the rest.
    """

    def __init__(self, ttl: float = 10.0, cleanup_interval: float = 30.0) -> None:
        self._cache: dict[str, tuple[Any, float]] = {}
        self.lock = threading.Lock()
        self._ttl = ttl
        self._cleanup_interval = cleanup_interval

    def get(self, key: str) -> Any | None:
        """Return the cached value, or None when key is missing or expired.

        A cached None result looks like a miss here; process() tells them apart.
        """
        with self.lock:
            _, value = self._lookup(key)
        return value

    def set(self, key: str, result: Any) -> None:
        with self.lock:
            self._store(key, result)

    def delete(self, key: str) -> None:
        with self.lock:
            self._cache.pop(key, None)

    def process(self, key: str, func: Callable[[], Any]) -> Any:
        """Return the cached result for key, or run func once and cache its result.

        The lookup and the PROCESSING marker are written under one lock acquisition,
        so a concurrent duplicate gets HTTP 409 instead of running func again. A
        result of None is cached like any other value. If func raises, the marker is
        removed so a retry can run.
        """
        with self.lock:
            hit, cached = self._lookup(key)
            if hit:
                if cached is CacheStatus.PROCESSING:
                    raise HTTPException(
                        status_code=HTTP_409_CONFLICT,
                        detail=f"Already Processing idempotency key: {key}",
                    )
                return cached
            self._store(key, CacheStatus.PROCESSING)

        try:
            result = func()
        except BaseException:
            self.delete(key)
            raise
        self.set(key, result)
        return result

    def evict_expired(self) -> None:
        with self.lock:
            now = time.monotonic()
            expired = [k for k, (_, exp) in self._cache.items() if now > exp]
            for k in expired:
                del self._cache[k]

    def _lookup(self, key: str) -> tuple[bool, Any]:
        """Return (hit, value) for key and drop it when expired; hold the lock."""
        entry = self._cache.get(key)
        if entry is None:
            return False, None
        value, expire_at = entry
        if time.monotonic() > expire_at:
            del self._cache[key]
            return False, None
        return True, value

    def _store(self, key: str, value: Any) -> None:
        """Store value for key with a fresh TTL; hold the lock."""
        self._cache[key] = (value, time.monotonic() + self._ttl)
