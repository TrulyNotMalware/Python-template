import asyncio

import pytest
from fastapi import HTTPException

from app.core.cache import AsyncIdempotencyCache
from app.core.cache.idempotency_cache import CacheStatus


class TestAsyncIdempotencyCacheProcess:
    @pytest.fixture
    def cache(self):
        instance = AsyncIdempotencyCache.__new__(AsyncIdempotencyCache)
        instance._cache = {}
        instance.lock = asyncio.Lock()
        instance._ttl = 10.0
        instance._cleanup_interval = 60.0
        return instance

    @pytest.mark.asyncio
    async def test_process_cache_miss_executes_func(self, cache):

        async def func():
            return {"status": "ok"}

        result = await cache.process("key1", func)
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_process_stores_result(self, cache):

        async def func():
            return {"status": "ok"}

        await cache.process("key1", func)
        cached = await cache.get("key1")
        assert cached == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_process_overwrites_processing_with_result(self, cache):

        async def func():
            return {"status": "ok"}

        await cache.process("key1", func)
        cached = await cache.get("key1")
        assert cached != CacheStatus.PROCESSING
        assert cached == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_process_cache_hit_returns_cached(self, cache):
        await cache.set("key1", {"status": "ok"})

        called = False

        async def func():
            nonlocal called
            called = True
            return {"status": "new"}

        result = await cache.process("key1", func)
        assert result == {"status": "ok"}
        assert called is False

    @pytest.mark.asyncio
    async def test_process_processing_raises_409(self, cache):
        await cache.set("key1", CacheStatus.PROCESSING)

        with pytest.raises(HTTPException) as exc:
            await cache.process("key1", lambda: asyncio.sleep(0))
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_process_func_exception_deletes_key(self, cache):
        async def failing_func():
            raise ValueError("실패")

        with pytest.raises(ValueError):
            await cache.process("key1", failing_func)

        assert await cache.get("key1") is None

    @pytest.mark.asyncio
    async def test_process_func_exception_reraises(self, cache):

        async def failing_func():
            raise ValueError("실패")

        with pytest.raises(ValueError, match="실패"):
            await cache.process("key1", failing_func)

    @pytest.mark.asyncio
    async def test_process_sets_processing_before_func(self, cache):
        processing_status = None

        async def func():
            nonlocal processing_status
            processing_status = await cache.get("key1")
            return {"status": "ok"}

        await cache.process("key1", func)
        assert processing_status == CacheStatus.PROCESSING
