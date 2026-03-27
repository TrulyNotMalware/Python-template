import asyncio
import functools
import hashlib
import json
import time
from collections.abc import Callable
from enum import Enum
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from app.core.utils import Singleton


class CacheStatus(Enum):
    PROCESSING = "PROCESSING"


class AsyncIdempotencyCache(metaclass=Singleton):
    def __init__(self, ttl: float = 10.0, cleanup_interval: float = 30.0) -> None:
        self._cache: dict = {}
        self.lock = asyncio.Lock()
        self._ttl = ttl
        self._cleanup_interval = cleanup_interval

    async def process(self, key: str, func: Callable) -> Any:
        cached = await self.get(key)
        if cached == CacheStatus.PROCESSING:
            raise HTTPException(status_code=409, detail="Already processing")
        if cached is not None:
            return cached

        await self.set(key, CacheStatus.PROCESSING)
        try:
            result = await func()
            await self.set(key, result)
            return result
        except Exception:
            await self.delete(key)
            raise

    async def get(self, key: str) -> Any | None:
        async with self.lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            result, expire_at = entry
            if time.monotonic() > expire_at:
                del self._cache[key]
                return None
            return result

    async def set(self, key: str, result: Any) -> None:
        async with self.lock:
            self._cache[key] = (result, time.monotonic() + self._ttl)

    async def delete(self, key: str) -> None:
        async with self.lock:
            self._cache.pop(key, None)

    async def evict_loop(self) -> None:
        while True:
            await asyncio.sleep(self._cleanup_interval)
            async with self.lock:
                now = time.monotonic()
                expired = [k for k, (_, exp) in self._cache.items() if now > exp]
                for k in expired:
                    del self._cache[k]


cache_manager = AsyncIdempotencyCache(ttl=10.0, cleanup_interval=30.0)


def generate_idempotency_key(
    dto: BaseModel,
    exclude: set[str] = None,
    extra: dict[str, Any] = None,
) -> str:
    data = dto.model_dump(exclude=exclude)
    if extra:
        data.update(extra)
    payload = json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def idempotent(exclude: set[str] = None) -> Callable[[Callable], Callable]:
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            dto = next((v for v in kwargs.values() if isinstance(v, BaseModel)), None)
            if dto is None:
                return await func(*args, **kwargs)

            key = generate_idempotency_key(dto, exclude=exclude)

            cached = await cache_manager.get(key)
            if cached is not None:
                return cached

            result = await func(*args, **kwargs)
            await cache_manager.set(key, result)
            return result

        return wrapper

    return decorator


class QueryIdempotencyDto(BaseModel):
    endpoint: str
    params: dict = {}

    model_config = {"frozen": True}
