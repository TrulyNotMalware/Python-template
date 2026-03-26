import asyncio
import hashlib
import json
import time
from typing import Any

from pydantic import BaseModel

from app.core.utils import Singleton


class AsyncIdempotencyCache(metaclass=Singleton):
    def __init__(self, ttl: float = 10.0, cleanup_interval: float = 30.0) -> None:
        self._cache: dict = {}
        self._lock = asyncio.Lock()
        self._ttl = ttl
        self._cleanup_interval = cleanup_interval

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            result, expire_at = entry
            if time.monotonic() > expire_at:
                del self._cache[key]
                return None
            return result

    async def set(self, key: str, result: Any) -> None:
        async with self._lock:
            self._cache[key] = (result, time.monotonic() + self._ttl)

    async def evict_loop(self) -> None:
        while True:
            await asyncio.sleep(self._cleanup_interval)
            async with self._lock:
                now = time.monotonic()
                expired = [k for k, (_, exp) in self._cache.items() if now > exp]
                for k in expired:
                    del self._cache[k]


cache_manager = AsyncIdempotencyCache(ttl=10.0, cleanup_interval=30.0)


def generate_idempotency_key(dto: BaseModel, exclude: set[str] = None) -> str:
    payload = json.dumps(
        dto.model_dump(exclude=exclude),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()
