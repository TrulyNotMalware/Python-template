import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from unittest.mock import patch
from uuid import UUID

from pydantic import BaseModel

from app.core.cache.idempotency_cache import (
    AsyncIdempotencyCache,
    generate_idempotency_key,
)

MODULE = "time.monotonic"


class SampleDto(BaseModel):
    amount: int
    to: str
    currency: str = "KRW"


class Channel(StrEnum):
    WEB = "web"
    APP = "app"


class TypedDto(BaseModel):
    order_id: UUID
    amount: Decimal
    requested_at: datetime
    channel: Channel


ORDER_ID = UUID("12345678-1234-5678-1234-567812345678")
REQUESTED_AT = datetime(2026, 10, 7, 9, 30, tzinfo=UTC)


def _typed_dto(amount: str = "1000.50", channel: Channel = Channel.WEB) -> TypedDto:
    return TypedDto(
        order_id=ORDER_ID,
        amount=Decimal(amount),
        requested_at=REQUESTED_AT,
        channel=channel,
    )


class TestAsyncIdempotencyCache:
    async def test_set_and_get(self, async_cache: AsyncIdempotencyCache) -> None:
        await async_cache.set("key1", {"status": "ok"})
        result = await async_cache.get("key1")
        assert result == {"status": "ok"}

    async def test_get_missing_key(self, async_cache: AsyncIdempotencyCache) -> None:
        result = await async_cache.get("nonexistent")
        assert result is None

    async def test_ttl_expired(self, async_cache: AsyncIdempotencyCache) -> None:
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 2.0]):
            await async_cache.set("key1", "value")
            result = await async_cache.get("key1")
        assert result is None

    async def test_ttl_not_expired(self, async_cache: AsyncIdempotencyCache) -> None:
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 0.5]):
            await async_cache.set("key1", "value")
            result = await async_cache.get("key1")
        assert result == "value"

    async def test_expired_key_removed_from_cache(
        self, async_cache: AsyncIdempotencyCache
    ) -> None:
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 2.0]):
            await async_cache.set("key1", "value")
            await async_cache.get("key1")
        assert "key1" not in async_cache._cache

    async def test_evict_expired_removes_expired(
        self, async_cache: AsyncIdempotencyCache
    ) -> None:
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 2.0]):
            await async_cache.set("key1", "value")
            await async_cache.evict_expired()
        assert "key1" not in async_cache._cache

    async def test_evict_expired_keeps_valid(
        self, async_cache: AsyncIdempotencyCache
    ) -> None:
        base = time.monotonic()
        with patch(MODULE, side_effect=[base, base + 0.5]):
            await async_cache.set("key1", "value")
            await async_cache.evict_expired()
        assert "key1" in async_cache._cache

    async def test_concurrent_set_get(self, async_cache: AsyncIdempotencyCache) -> None:
        async def writer(i: int) -> None:
            await async_cache.set(f"key{i}", i)

        async def reader(i: int) -> int | None:
            return await async_cache.get(f"key{i}")

        await asyncio.gather(*[writer(i) for i in range(50)])
        results = await asyncio.gather(*[reader(i) for i in range(50)])
        assert results == list(range(50))


class TestGenerateIdempotencyKey:
    def test_same_dto_same_key(self) -> None:
        r1 = SampleDto(amount=1000, to="alice")
        r2 = SampleDto(amount=1000, to="alice")
        assert generate_idempotency_key(r1) == generate_idempotency_key(r2)

    def test_different_dto_different_key(self) -> None:
        r1 = SampleDto(amount=1000, to="alice")
        r2 = SampleDto(amount=2000, to="alice")
        assert generate_idempotency_key(r1) != generate_idempotency_key(r2)

    def test_field_order_does_not_matter(self) -> None:
        r1 = SampleDto(amount=1000, to="alice", currency="USD")
        r2 = SampleDto(currency="USD", to="alice", amount=1000)
        assert generate_idempotency_key(r1) == generate_idempotency_key(r2)

    def test_exclude_fields(self) -> None:
        r1 = SampleDto(amount=1000, to="alice", currency="KRW")
        r2 = SampleDto(amount=1000, to="alice", currency="USD")
        key1 = generate_idempotency_key(r1, exclude={"currency"})
        key2 = generate_idempotency_key(r2, exclude={"currency"})
        assert key1 == key2

    def test_returns_sha256_hex(self) -> None:
        dto = SampleDto(amount=1000, to="alice")
        key = generate_idempotency_key(dto)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_extra_same_value_same_key(self) -> None:
        dto = SampleDto(amount=1000, to="alice")
        key1 = generate_idempotency_key(dto, extra={"user_id": 123})
        key2 = generate_idempotency_key(dto, extra={"user_id": 123})
        assert key1 == key2

    def test_extra_different_value_different_key(self) -> None:
        dto = SampleDto(amount=1000, to="alice")
        key1 = generate_idempotency_key(dto, extra={"user_id": 123})
        key2 = generate_idempotency_key(dto, extra={"user_id": 456})
        assert key1 != key2

    def test_extra_changes_key_from_no_extra(self) -> None:
        dto = SampleDto(amount=1000, to="alice")
        key1 = generate_idempotency_key(dto)
        key2 = generate_idempotency_key(dto, extra={"user_id": 123})
        assert key1 != key2

    def test_extra_none_equals_no_extra(self) -> None:
        dto = SampleDto(amount=1000, to="alice")
        key1 = generate_idempotency_key(dto, extra=None)
        key2 = generate_idempotency_key(dto)
        assert key1 == key2

    def test_extra_multiple_fields(self) -> None:
        dto = SampleDto(amount=1000, to="alice")
        key1 = generate_idempotency_key(dto, extra={"user_id": 123, "tenant_id": "A"})
        key2 = generate_idempotency_key(dto, extra={"user_id": 123, "tenant_id": "A"})
        assert key1 == key2

    def test_extra_multiple_fields_different_value(self) -> None:
        dto = SampleDto(amount=1000, to="alice")
        key1 = generate_idempotency_key(dto, extra={"user_id": 123, "tenant_id": "A"})
        key2 = generate_idempotency_key(dto, extra={"user_id": 123, "tenant_id": "B"})
        assert key1 != key2

    def test_extra_key_order_does_not_matter(self) -> None:
        dto = SampleDto(amount=1000, to="alice")
        key1 = generate_idempotency_key(dto, extra={"user_id": 123, "tenant_id": "A"})
        key2 = generate_idempotency_key(dto, extra={"tenant_id": "A", "user_id": 123})
        assert key1 == key2

    def test_extra_with_exclude(self) -> None:
        r1 = SampleDto(amount=1000, to="alice", currency="KRW")
        r2 = SampleDto(amount=1000, to="alice", currency="USD")
        key1 = generate_idempotency_key(
            r1, exclude={"currency"}, extra={"user_id": 123}
        )
        key2 = generate_idempotency_key(
            r2, exclude={"currency"}, extra={"user_id": 123}
        )
        assert key1 == key2


class TestGenerateIdempotencyKeyJsonTypes:
    def test_non_json_native_fields_produce_key(self) -> None:
        key = generate_idempotency_key(_typed_dto())
        assert len(key) == 64

    def test_same_typed_values_same_key(self) -> None:
        assert generate_idempotency_key(_typed_dto()) == generate_idempotency_key(
            _typed_dto()
        )

    def test_different_decimal_different_key(self) -> None:
        key1 = generate_idempotency_key(_typed_dto(amount="1000.50"))
        key2 = generate_idempotency_key(_typed_dto(amount="1000.51"))
        assert key1 != key2

    def test_different_enum_different_key(self) -> None:
        key1 = generate_idempotency_key(_typed_dto(channel=Channel.WEB))
        key2 = generate_idempotency_key(_typed_dto(channel=Channel.APP))
        assert key1 != key2

    def test_extra_does_not_overwrite_dto_field(self) -> None:
        r1 = SampleDto(amount=1000, to="alice")
        r2 = SampleDto(amount=1000, to="bob")
        key1 = generate_idempotency_key(r1, extra={"to": "carol"})
        key2 = generate_idempotency_key(r2, extra={"to": "carol"})
        assert key1 != key2
