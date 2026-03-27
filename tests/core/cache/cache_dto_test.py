import pytest
from pydantic import ValidationError

from app.core.cache.idempotency_cache import (
    QueryIdempotencyDto,
    generate_idempotency_key,
)


class TestQueryIdempotencyDto:
    def test_same_params_same_key(self):
        dto1 = QueryIdempotencyDto(
            endpoint="/users", params={"status": "active", "page": 1}
        )
        dto2 = QueryIdempotencyDto(
            endpoint="/users", params={"status": "active", "page": 1}
        )
        assert generate_idempotency_key(dto1) == generate_idempotency_key(dto2)

    def test_different_endpoint_different_key(self):
        dto1 = QueryIdempotencyDto(endpoint="/users", params={"page": 1})
        dto2 = QueryIdempotencyDto(endpoint="/orders", params={"page": 1})
        assert generate_idempotency_key(dto1) != generate_idempotency_key(dto2)

    def test_different_params_different_key(self):
        dto1 = QueryIdempotencyDto(endpoint="/users", params={"status": "active"})
        dto2 = QueryIdempotencyDto(endpoint="/users", params={"status": "inactive"})
        assert generate_idempotency_key(dto1) != generate_idempotency_key(dto2)

    def test_param_order_does_not_matter(self):
        """params 딕셔너리 순서가 달라도 동일한 키"""
        dto1 = QueryIdempotencyDto(
            endpoint="/users", params={"status": "active", "page": 1}
        )
        dto2 = QueryIdempotencyDto(
            endpoint="/users", params={"page": 1, "status": "active"}
        )
        assert generate_idempotency_key(dto1) == generate_idempotency_key(dto2)

    def test_empty_params_same_key(self):
        dto1 = QueryIdempotencyDto(endpoint="/users")
        dto2 = QueryIdempotencyDto(endpoint="/users", params={})
        assert generate_idempotency_key(dto1) == generate_idempotency_key(dto2)

    def test_empty_params_different_from_with_params(self):
        dto1 = QueryIdempotencyDto(endpoint="/users")
        dto2 = QueryIdempotencyDto(endpoint="/users", params={"page": 1})
        assert generate_idempotency_key(dto1) != generate_idempotency_key(dto2)

    def test_frozen_model_immutable(self):
        dto = QueryIdempotencyDto(endpoint="/users", params={"page": 1})
        with pytest.raises(ValidationError):
            dto.endpoint = "/orders"

    def test_extra_user_id(self):
        dto = QueryIdempotencyDto(endpoint="/users", params={"page": 1})
        key1 = generate_idempotency_key(dto, extra={"user_id": 123})
        key2 = generate_idempotency_key(dto, extra={"user_id": 456})
        assert key1 != key2

    def test_extra_same_user_id_same_key(self):
        dto1 = QueryIdempotencyDto(endpoint="/users", params={"page": 1})
        dto2 = QueryIdempotencyDto(endpoint="/users", params={"page": 1})
        key1 = generate_idempotency_key(dto1, extra={"user_id": 123})
        key2 = generate_idempotency_key(dto2, extra={"user_id": 123})
        assert key1 == key2
