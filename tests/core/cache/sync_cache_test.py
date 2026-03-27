import threading
import time
from unittest.mock import patch

import pytest

from app.core.cache.sync_idempotency_cache import SyncIdempotencyCache

MODULE = "time.monotonic"


@pytest.fixture
def cache():
    instance = SyncIdempotencyCache.__new__(SyncIdempotencyCache)
    instance._cache = {}
    instance.lock = threading.Lock()
    instance._ttl = 1.0
    instance._cleanup_interval = 60.0
    return instance


class TestSyncIdempotencyCache:
    def test_set_and_get(self, cache):
        cache.set("key1", {"status": "ok"})
        assert cache.get("key1") == {"status": "ok"}

    def test_get_missing_key(self, cache):
        assert cache.get("nonexistent") is None

    def test_ttl_expired(self, cache):
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 2.0]):
            cache.set("key1", "value")
            result = cache.get("key1")
        assert result is None

    def test_ttl_not_expired(self, cache):
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 0.5]):
            cache.set("key1", "value")
            result = cache.get("key1")
        assert result == "value"

    def test_expired_key_removed_from_cache(self, cache):
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 2.0]):
            cache.set("key1", "value")
            cache.get("key1")
        assert "key1" not in cache._cache

    def test_overwrite_existing_key(self, cache):
        cache.set("key1", "first")
        cache.set("key1", "second")
        assert cache.get("key1") == "second"

    def test_delete_existing_key(self, cache):
        cache.set("key1", "value")
        cache.delete("key1")
        assert cache.get("key1") is None

    def test_delete_missing_key_no_error(self, cache):
        cache.delete("nonexistent")  # 예외 없이 통과

    def test_evict_expired(self, cache):
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 2.0]):
            cache.set("key1", "value")
            cache.evict_expired()
        assert "key1" not in cache._cache

    def test_evict_keeps_valid(self, cache):
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 0.5]):
            cache.set("key1", "value")
            cache.evict_expired()
        assert "key1" in cache._cache

    def test_concurrent_set_get(self, cache):

        def writer(i):
            cache.set(f"key{i}", i)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i in range(50):
            assert cache.get(f"key{i}") == i
