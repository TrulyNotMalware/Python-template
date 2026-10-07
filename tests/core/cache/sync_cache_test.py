import threading
import time
from unittest.mock import patch

from app.core.cache.sync_idempotency_cache import SyncIdempotencyCache

MODULE = "time.monotonic"


class TestSyncIdempotencyCache:
    def test_set_and_get(self, sync_cache: SyncIdempotencyCache) -> None:
        sync_cache.set("key1", {"status": "ok"})
        assert sync_cache.get("key1") == {"status": "ok"}

    def test_get_missing_key(self, sync_cache: SyncIdempotencyCache) -> None:
        assert sync_cache.get("nonexistent") is None

    def test_ttl_expired(self, sync_cache: SyncIdempotencyCache) -> None:
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 2.0]):
            sync_cache.set("key1", "value")
            result = sync_cache.get("key1")
        assert result is None

    def test_ttl_not_expired(self, sync_cache: SyncIdempotencyCache) -> None:
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 0.5]):
            sync_cache.set("key1", "value")
            result = sync_cache.get("key1")
        assert result == "value"

    def test_expired_key_removed_from_cache(
        self, sync_cache: SyncIdempotencyCache
    ) -> None:
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 2.0]):
            sync_cache.set("key1", "value")
            sync_cache.get("key1")
        assert "key1" not in sync_cache._cache

    def test_overwrite_existing_key(self, sync_cache: SyncIdempotencyCache) -> None:
        sync_cache.set("key1", "first")
        sync_cache.set("key1", "second")
        assert sync_cache.get("key1") == "second"

    def test_delete_existing_key(self, sync_cache: SyncIdempotencyCache) -> None:
        sync_cache.set("key1", "value")
        sync_cache.delete("key1")
        assert sync_cache.get("key1") is None

    def test_delete_missing_key_no_error(
        self, sync_cache: SyncIdempotencyCache
    ) -> None:
        sync_cache.delete("nonexistent")

    def test_evict_expired(self, sync_cache: SyncIdempotencyCache) -> None:
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 2.0]):
            sync_cache.set("key1", "value")
            sync_cache.evict_expired()
        assert "key1" not in sync_cache._cache

    def test_evict_keeps_valid(self, sync_cache: SyncIdempotencyCache) -> None:
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 0.5]):
            sync_cache.set("key1", "value")
            sync_cache.evict_expired()
        assert "key1" in sync_cache._cache

    def test_concurrent_set_get(self, sync_cache: SyncIdempotencyCache) -> None:

        def writer(i: int) -> None:
            sync_cache.set(f"key{i}", i)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i in range(50):
            assert sync_cache.get(f"key{i}") == i
