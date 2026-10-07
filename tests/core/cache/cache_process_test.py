import asyncio

import pytest
from fastapi import HTTPException

from app.core.cache import AsyncIdempotencyCache
from app.core.cache.protocol import CacheStatus


class TestAsyncIdempotencyCacheProcess:
    async def test_process_cache_miss_executes_func(
        self, async_cache: AsyncIdempotencyCache
    ) -> None:

        async def func() -> dict[str, str]:
            return {"status": "ok"}

        result = await async_cache.process("key1", func)
        assert result == {"status": "ok"}

    async def test_process_stores_result(
        self, async_cache: AsyncIdempotencyCache
    ) -> None:

        async def func() -> dict[str, str]:
            return {"status": "ok"}

        await async_cache.process("key1", func)
        cached = await async_cache.get("key1")
        assert cached == {"status": "ok"}

    async def test_process_overwrites_processing_with_result(
        self, async_cache: AsyncIdempotencyCache
    ) -> None:

        async def func() -> dict[str, str]:
            return {"status": "ok"}

        await async_cache.process("key1", func)
        cached = await async_cache.get("key1")
        assert cached != CacheStatus.PROCESSING
        assert cached == {"status": "ok"}

    async def test_process_cache_hit_returns_cached(
        self, async_cache: AsyncIdempotencyCache
    ) -> None:
        await async_cache.set("key1", {"status": "ok"})

        called = False

        async def func() -> dict[str, str]:
            nonlocal called
            called = True
            return {"status": "new"}

        result = await async_cache.process("key1", func)
        assert result == {"status": "ok"}
        assert called is False

    async def test_process_processing_raises_409(
        self, async_cache: AsyncIdempotencyCache
    ) -> None:
        await async_cache.set("key1", CacheStatus.PROCESSING)

        with pytest.raises(HTTPException) as exc:
            await async_cache.process("key1", lambda: asyncio.sleep(0))
        assert exc.value.status_code == 409

    async def test_process_func_exception_deletes_key(
        self, async_cache: AsyncIdempotencyCache
    ) -> None:
        async def failing_func() -> None:
            raise ValueError("실패")

        with pytest.raises(ValueError, match="실패"):
            await async_cache.process("key1", failing_func)

        assert await async_cache.get("key1") is None

    async def test_process_func_exception_reraises(
        self, async_cache: AsyncIdempotencyCache
    ) -> None:

        async def failing_func() -> None:
            raise ValueError("실패")

        with pytest.raises(ValueError, match="실패"):
            await async_cache.process("key1", failing_func)

    async def test_process_sets_processing_before_func(
        self, async_cache: AsyncIdempotencyCache
    ) -> None:
        processing_status = None

        async def func() -> dict[str, str]:
            nonlocal processing_status
            processing_status = await async_cache.get("key1")
            return {"status": "ok"}

        await async_cache.process("key1", func)
        assert processing_status == CacheStatus.PROCESSING

    async def test_process_none_result_is_not_rerun(
        self, async_cache: AsyncIdempotencyCache
    ) -> None:
        calls = 0

        async def func() -> None:
            nonlocal calls
            calls += 1

        assert await async_cache.process("key1", func) is None
        assert await async_cache.process("key1", func) is None
        assert calls == 1

    async def test_process_concurrent_duplicate_raises_409(
        self, async_cache: AsyncIdempotencyCache
    ) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def func() -> dict[str, str]:
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()
            return {"status": "ok"}

        first = asyncio.create_task(async_cache.process("key1", func))
        await started.wait()

        try:
            with pytest.raises(HTTPException) as exc:
                async with asyncio.timeout(1):
                    await async_cache.process("key1", func)
        finally:
            release.set()
        assert exc.value.status_code == 409
        assert await first == {"status": "ok"}
        assert calls == 1

    async def test_process_cancelled_task_deletes_marker(
        self, async_cache: AsyncIdempotencyCache
    ) -> None:
        started = asyncio.Event()

        async def never_finishes() -> None:
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(async_cache.process("key1", never_finishes))
        await started.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert "key1" not in async_cache._cache

        async def func() -> str:
            return "retried"

        assert await async_cache.process("key1", func) == "retried"

    async def test_process_timeout_deletes_marker(
        self, async_cache: AsyncIdempotencyCache
    ) -> None:

        async def never_finishes() -> None:
            await asyncio.Event().wait()

        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.01):
                await async_cache.process("key1", never_finishes)

        assert "key1" not in async_cache._cache
