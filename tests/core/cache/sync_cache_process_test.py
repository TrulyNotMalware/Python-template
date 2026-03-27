import threading

import pytest
from fastapi import HTTPException

from app.core.cache.protocol import CacheStatus
from app.core.cache.sync_idempotency_cache import SyncIdempotencyCache


@pytest.fixture
def cache():
    instance = SyncIdempotencyCache.__new__(SyncIdempotencyCache)
    instance._cache = {}
    instance.lock = threading.Lock()
    instance._ttl = 1.0
    instance._cleanup_interval = 60.0
    return instance


class TestSyncIdempotencyCacheProcess:
    def test_process_cache_miss_executes_func(self, cache):
        result = cache.process("key1", lambda: {"status": "ok"})
        assert result == {"status": "ok"}

    def test_process_stores_result(self, cache):
        cache.process("key1", lambda: {"status": "ok"})
        assert cache.get("key1") == {"status": "ok"}

    def test_process_cache_hit_returns_cached(self, cache):
        cache.set("key1", {"status": "cached"})

        called = False

        def func():
            nonlocal called
            called = True
            return {"status": "new"}

        result = cache.process("key1", func)
        assert result == {"status": "cached"}
        assert called is False

    def test_process_cache_hit_does_not_store(self, cache):
        cache.set("key1", {"status": "cached"})
        cache.process("key1", lambda: {"status": "new"})
        assert cache.get("key1") == {"status": "cached"}

    def test_process_processing_raises_409(self, cache):
        cache.set("key1", CacheStatus.PROCESSING)

        with pytest.raises(HTTPException) as exc:
            cache.process("key1", lambda: {"status": "ok"})
        assert exc.value.status_code == 409

    def test_process_func_exception_deletes_key(self, cache):

        def failing_func():
            raise ValueError("실패")

        with pytest.raises(ValueError):
            cache.process("key1", failing_func)

        assert cache.get("key1") is None

    def test_process_func_exception_reraises(self, cache):
        def failing_func():
            raise ValueError("실패")

        with pytest.raises(ValueError, match="실패"):
            cache.process("key1", failing_func)

    def test_process_sets_processing_before_func(self, cache):
        processing_status = None

        def func():
            nonlocal processing_status
            processing_status = cache.get("key1")
            return {"status": "ok"}

        cache.process("key1", func)
        assert processing_status == CacheStatus.PROCESSING

    def test_process_overwrites_processing_with_result(self, cache):
        cache.process("key1", lambda: {"status": "ok"})
        cached = cache.get("key1")
        assert cached != CacheStatus.PROCESSING
        assert cached == {"status": "ok"}

    def test_process_concurrent_requests(self, cache):
        import time

        results = []

        def func():
            time.sleep(0.1)  # 처리 시간 시뮬레이션
            return {"status": "ok"}

        def request():
            try:
                result = cache.process("key1", func)
                results.append(("ok", result))
            except HTTPException as e:
                results.append(("409", e.status_code))

        threads = [threading.Thread(target=request) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        ok_count = sum(1 for status, _ in results if status == "ok")
        conflict_count = sum(1 for status, _ in results if status == "409")

        assert ok_count == 1
        assert conflict_count == 4
