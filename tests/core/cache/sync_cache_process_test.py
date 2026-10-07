import functools
import sys
import threading
from collections import Counter

import pytest
from fastapi import HTTPException

from app.core.cache.protocol import CacheStatus
from app.core.cache.sync_idempotency_cache import SyncIdempotencyCache


class TestSyncIdempotencyCacheProcess:
    def test_process_cache_miss_executes_func(
        self, sync_cache: SyncIdempotencyCache
    ) -> None:
        result = sync_cache.process("key1", lambda: {"status": "ok"})
        assert result == {"status": "ok"}

    def test_process_stores_result(self, sync_cache: SyncIdempotencyCache) -> None:
        sync_cache.process("key1", lambda: {"status": "ok"})
        assert sync_cache.get("key1") == {"status": "ok"}

    def test_process_cache_hit_returns_cached(
        self, sync_cache: SyncIdempotencyCache
    ) -> None:
        sync_cache.set("key1", {"status": "cached"})

        called = False

        def func() -> dict[str, str]:
            nonlocal called
            called = True
            return {"status": "new"}

        result = sync_cache.process("key1", func)
        assert result == {"status": "cached"}
        assert called is False

    def test_process_cache_hit_does_not_store(
        self, sync_cache: SyncIdempotencyCache
    ) -> None:
        sync_cache.set("key1", {"status": "cached"})
        sync_cache.process("key1", lambda: {"status": "new"})
        assert sync_cache.get("key1") == {"status": "cached"}

    def test_process_processing_raises_409(
        self, sync_cache: SyncIdempotencyCache
    ) -> None:
        sync_cache.set("key1", CacheStatus.PROCESSING)

        with pytest.raises(HTTPException) as exc:
            sync_cache.process("key1", lambda: {"status": "ok"})
        assert exc.value.status_code == 409

    def test_process_func_exception_deletes_key(
        self, sync_cache: SyncIdempotencyCache
    ) -> None:

        def failing_func() -> None:
            raise ValueError("실패")

        with pytest.raises(ValueError, match="실패"):
            sync_cache.process("key1", failing_func)

        assert sync_cache.get("key1") is None

    def test_process_func_exception_reraises(
        self, sync_cache: SyncIdempotencyCache
    ) -> None:
        def failing_func() -> None:
            raise ValueError("실패")

        with pytest.raises(ValueError, match="실패"):
            sync_cache.process("key1", failing_func)

    def test_process_sets_processing_before_func(
        self, sync_cache: SyncIdempotencyCache
    ) -> None:
        processing_status = None

        def func() -> dict[str, str]:
            nonlocal processing_status
            processing_status = sync_cache.get("key1")
            return {"status": "ok"}

        sync_cache.process("key1", func)
        assert processing_status == CacheStatus.PROCESSING

    def test_process_overwrites_processing_with_result(
        self, sync_cache: SyncIdempotencyCache
    ) -> None:
        sync_cache.process("key1", lambda: {"status": "ok"})
        cached = sync_cache.get("key1")
        assert cached != CacheStatus.PROCESSING
        assert cached == {"status": "ok"}

    def test_process_none_result_is_not_rerun(
        self, sync_cache: SyncIdempotencyCache
    ) -> None:
        calls = 0

        def func() -> None:
            nonlocal calls
            calls += 1

        assert sync_cache.process("key1", func) is None
        assert sync_cache.process("key1", func) is None
        assert calls == 1

    def test_process_simultaneous_start_runs_func_once_per_key(
        self, sync_cache: SyncIdempotencyCache
    ) -> None:
        thread_count = 8
        rounds = 500
        barrier = threading.Barrier(thread_count, timeout=10)
        calls: Counter[str] = Counter()
        calls_lock = threading.Lock()
        unexpected: list[BaseException] = []

        def run(key: str) -> str:
            with calls_lock:
                calls[key] += 1
            return key

        def worker() -> None:
            for round_no in range(rounds):
                key = f"key{round_no}"
                barrier.wait()
                try:
                    sync_cache.process(key, functools.partial(run, key))
                except HTTPException as exc:
                    if exc.status_code != 409:
                        unexpected.append(exc)
                except BaseException as exc:
                    unexpected.append(exc)
                    barrier.abort()
                    return

        # A tiny switch interval makes the GIL hand over between the lookup and the
        # PROCESSING write; without it the check-then-set race almost never shows.
        switch_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            threads = [threading.Thread(target=worker) for _ in range(thread_count)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        finally:
            sys.setswitchinterval(switch_interval)

        assert unexpected == []
        assert calls == Counter({f"key{i}": 1 for i in range(rounds)})
