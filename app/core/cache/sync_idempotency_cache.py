import threading
import time
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from starlette.status import HTTP_409_CONFLICT

from app.core.cache.protocol import CacheStatus
from app.core.utils import Singleton


class SyncIdempotencyCache(metaclass=Singleton):
    def __init__(self, ttl: float = 10.0, cleanup_interval: float = 30.0) -> None:
        self._cache: dict = {}
        self.lock = threading.Lock()
        self._ttl = ttl
        self._cleanup_interval = cleanup_interval

    def get(self, key: str) -> Any | None:
        with self.lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            result, expire_at = entry
            if time.monotonic() > expire_at:
                del self._cache[key]
                return None
            return result

    def set(self, key: str, result: Any) -> None:
        with self.lock:
            self._cache[key] = (result, time.monotonic() + self._ttl)

    def delete(self, key: str) -> None:
        with self.lock:
            self._cache.pop(key, None)

    def process(self, key: str, func: Callable) -> Any:
        cached = self.get(key)
        if cached == CacheStatus.PROCESSING:
            raise HTTPException(
                status_code=HTTP_409_CONFLICT,
                detail=f"Already Processing idempotency key: {key}",
            )
        if cached is not None:
            return cached

        self.set(key, CacheStatus.PROCESSING)
        try:
            result = func()
            self.set(key, result)
            return result
        except Exception:
            self.delete(key)
            raise

    def evict_expired(self) -> None:
        with self.lock:
            now = time.monotonic()
            expired = [k for k, (_, exp) in self._cache.items() if now > exp]
            for k in expired:
                del self._cache[k]
