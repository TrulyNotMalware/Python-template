import asyncio
import time
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from app.core.cache.idempotency_cache import (
    AsyncIdempotencyCache,
    generate_idempotency_key,
)

MODULE = "time.monotonic"


@pytest.fixture
def cache() -> AsyncIdempotencyCache:  # Singleton class
    instance = AsyncIdempotencyCache.__new__(AsyncIdempotencyCache)
    instance._cache = {}
    instance.lock = asyncio.Lock()
    instance._ttl = 1.0
    instance._cleanup_interval = 60.0
    return instance


class SampleDto(BaseModel):
    amount: int
    to: str
    currency: str = "KRW"


class TestAsyncIdempotencyCache:
    @pytest.mark.asyncio
    async def test_set_and_get(self, cache):
        await cache.set("key1", {"status": "ok"})
        result = await cache.get("key1")
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_get_missing_key(self, cache):
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_ttl_expired(self, cache):
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 2.0]):
            await cache.set("key1", "value")
            result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_ttl_not_expired(self, cache):
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 0.5]):
            await cache.set("key1", "value")
            result = await cache.get("key1")
        assert result == "value"

    @pytest.mark.asyncio
    async def test_expired_key_removed_from_cache(self, cache):
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 2.0]):
            await cache.set("key1", "value")
            await cache.get("key1")
        assert "key1" not in cache._cache

    @pytest.mark.asyncio
    async def test_evict_loop_removes_expired(self, cache):
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 2.0]):
            await cache.set("key1", "value")
            await _run_single_evict(cache)
        assert "key1" not in cache._cache

    @pytest.mark.asyncio
    async def test_evict_loop_keeps_valid(self, cache):
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 0.5]):
            await cache.set("key1", "value")
            await _run_single_evict(cache)
        assert "key1" in cache._cache

    @pytest.mark.asyncio
    async def test_concurrent_set_get(self, cache):
        async def writer(i):
            await cache.set(f"key{i}", i)

        async def reader(i):
            return await cache.get(f"key{i}")

        await asyncio.gather(*[writer(i) for i in range(50)])
        results = await asyncio.gather(*[reader(i) for i in range(50)])
        assert results == list(range(50))


async def _run_single_evict(cache: AsyncIdempotencyCache):
    async with cache.lock:
        now = time.monotonic()
        expired = [k for k, (_, exp) in cache._cache.items() if now > exp]
        for k in expired:
            del cache._cache[k]


class TestGenerateIdempotencyKey:
    def test_same_dto_same_key(self):
        r1 = SampleDto(amount=1000, to="alice")
        r2 = SampleDto(amount=1000, to="alice")
        assert generate_idempotency_key(r1) == generate_idempotency_key(r2)

    def test_different_dto_different_key(self):
        r1 = SampleDto(amount=1000, to="alice")
        r2 = SampleDto(amount=2000, to="alice")
        assert generate_idempotency_key(r1) != generate_idempotency_key(r2)

    def test_field_order_does_not_matter(self):
        r1 = SampleDto(amount=1000, to="alice", currency="USD")
        r2 = SampleDto(currency="USD", to="alice", amount=1000)
        assert generate_idempotency_key(r1) == generate_idempotency_key(r2)

    def test_exclude_fields(self):
        r1 = SampleDto(amount=1000, to="alice", currency="KRW")
        r2 = SampleDto(amount=1000, to="alice", currency="USD")
        key1 = generate_idempotency_key(r1, exclude={"currency"})
        key2 = generate_idempotency_key(r2, exclude={"currency"})
        assert key1 == key2

    def test_returns_sha256_hex(self):
        dto = SampleDto(amount=1000, to="alice")
        key = generate_idempotency_key(dto)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_extra_same_value_same_key(self):
        dto = SampleDto(amount=1000, to="alice")
        key1 = generate_idempotency_key(dto, extra={"user_id": 123})
        key2 = generate_idempotency_key(dto, extra={"user_id": 123})
        assert key1 == key2

    def test_extra_different_value_different_key(self):
        dto = SampleDto(amount=1000, to="alice")
        key1 = generate_idempotency_key(dto, extra={"user_id": 123})
        key2 = generate_idempotency_key(dto, extra={"user_id": 456})
        assert key1 != key2

    def test_extra_changes_key_from_no_extra(self):
        dto = SampleDto(amount=1000, to="alice")
        key1 = generate_idempotency_key(dto)
        key2 = generate_idempotency_key(dto, extra={"user_id": 123})
        assert key1 != key2

    def test_extra_none_equals_no_extra(self):
        dto = SampleDto(amount=1000, to="alice")
        key1 = generate_idempotency_key(dto, extra=None)
        key2 = generate_idempotency_key(dto)
        assert key1 == key2

    def test_extra_multiple_fields(self):
        dto = SampleDto(amount=1000, to="alice")
        key1 = generate_idempotency_key(dto, extra={"user_id": 123, "tenant_id": "A"})
        key2 = generate_idempotency_key(dto, extra={"user_id": 123, "tenant_id": "A"})
        assert key1 == key2

    def test_extra_multiple_fields_different_value(self):
        dto = SampleDto(amount=1000, to="alice")
        key1 = generate_idempotency_key(dto, extra={"user_id": 123, "tenant_id": "A"})
        key2 = generate_idempotency_key(dto, extra={"user_id": 123, "tenant_id": "B"})
        assert key1 != key2

    def test_extra_key_order_does_not_matter(self):
        dto = SampleDto(amount=1000, to="alice")
        key1 = generate_idempotency_key(dto, extra={"user_id": 123, "tenant_id": "A"})
        key2 = generate_idempotency_key(dto, extra={"tenant_id": "A", "user_id": 123})
        assert key1 == key2

    def test_extra_with_exclude(self):
        r1 = SampleDto(amount=1000, to="alice", currency="KRW")
        r2 = SampleDto(amount=1000, to="alice", currency="USD")
        key1 = generate_idempotency_key(
            r1, exclude={"currency"}, extra={"user_id": 123}
        )
        key2 = generate_idempotency_key(
            r2, exclude={"currency"}, extra={"user_id": 123}
        )
        assert key1 == key2
