import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any
from uuid import UUID

import pytest
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, SecretBytes, SecretStr

from app.core.cache import idempotency_cache
from app.core.cache.idempotency_cache import AsyncIdempotencyCache, idempotent


class TransferDto(BaseModel):
    amount: int
    to: str
    memo: str = ""


class CurrentUser(BaseModel):
    name: str
    memo: str = ""


class DepositDto(BaseModel):
    amount: int


class Priority(Enum):
    LOW = 1
    HIGH = 2


class PasswordChangeDto(BaseModel):
    new_password: SecretStr


class Handle:
    """A value pydantic cannot serialize."""


class UploadDto(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    handle: Handle


def current_user(x_user: Annotated[str, Header()]) -> CurrentUser:
    return CurrentUser(name=x_user)


@pytest.fixture
def manager(
    async_cache: AsyncIdempotencyCache, monkeypatch: pytest.MonkeyPatch
) -> AsyncIdempotencyCache:
    monkeypatch.setattr(idempotency_cache, "cache_manager", async_cache)
    return async_cache


@dataclass(frozen=True, slots=True)
class DepositApi:
    client: TestClient
    calls: list[tuple[str, int, int]]

    def post(self, user: str, account_id: int, amount: int) -> dict[str, Any]:
        response = self.client.post(
            f"/accounts/{account_id}/deposits",
            json={"amount": amount},
            headers={"X-User": user},
        )
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body


@pytest.fixture
def deposit_api(manager: AsyncIdempotencyCache) -> Iterator[DepositApi]:
    calls: list[tuple[str, int, int]] = []
    api = FastAPI()

    @api.post("/accounts/{account_id}/deposits")
    @idempotent()
    async def deposit(
        user: Annotated[CurrentUser, Depends(current_user)],
        account_id: int,
        body: DepositDto,
    ) -> dict[str, Any]:
        calls.append((user.name, account_id, body.amount))
        return {"user": user.name, "account_id": account_id, "amount": body.amount}

    with TestClient(api) as client:
        yield DepositApi(client=client, calls=calls)


class TestIdempotentThroughFastAPI:
    def test_same_user_body_and_path_is_cached(self, deposit_api: DepositApi) -> None:
        first = deposit_api.post("alice", account_id=1, amount=100)
        second = deposit_api.post("alice", account_id=1, amount=100)

        assert second == first
        assert deposit_api.calls == [("alice", 1, 100)]

    def test_different_body_runs_again(self, deposit_api: DepositApi) -> None:
        deposit_api.post("alice", account_id=1, amount=100)
        second = deposit_api.post("alice", account_id=1, amount=999)

        assert second["amount"] == 999
        assert deposit_api.calls == [("alice", 1, 100), ("alice", 1, 999)]

    def test_different_path_parameter_runs_again(self, deposit_api: DepositApi) -> None:
        deposit_api.post("alice", account_id=1, amount=100)
        second = deposit_api.post("alice", account_id=2, amount=100)

        assert second["account_id"] == 2
        assert deposit_api.calls == [("alice", 1, 100), ("alice", 2, 100)]

    def test_different_dependency_result_runs_again(
        self, deposit_api: DepositApi
    ) -> None:
        deposit_api.post("alice", account_id=1, amount=100)
        second = deposit_api.post("bob", account_id=1, amount=100)

        assert second["user"] == "bob"
        assert deposit_api.calls == [("alice", 1, 100), ("bob", 1, 100)]


class TestIdempotentDecorator:
    async def test_same_body_runs_once(self, manager: AsyncIdempotencyCache) -> None:
        calls = 0

        @idempotent()
        async def create(body: TransferDto) -> dict[str, int]:
            nonlocal calls
            calls += 1
            return {"call": calls}

        body = TransferDto(amount=1000, to="alice")
        assert await create(body=body) == {"call": 1}
        assert await create(body=body) == {"call": 1}
        assert calls == 1
        assert len(manager._cache) == 1

    async def test_positional_and_keyword_calls_share_key(
        self, manager: AsyncIdempotencyCache
    ) -> None:
        calls = 0

        @idempotent()
        async def create(body: TransferDto) -> int:
            nonlocal calls
            calls += 1
            return calls

        body = TransferDto(amount=1000, to="alice")
        assert await create(body) == 1
        assert await create(body=body) == 1
        assert calls == 1

    async def test_same_body_different_functions_do_not_collide(
        self, manager: AsyncIdempotencyCache
    ) -> None:

        @idempotent()
        async def create_transfer(body: TransferDto) -> str:
            return "transfer"

        @idempotent()
        async def create_refund(body: TransferDto) -> str:
            return "refund"

        body = TransferDto(amount=1000, to="alice")
        assert await create_transfer(body=body) == "transfer"
        assert await create_refund(body=body) == "refund"
        assert len(manager._cache) == 2

    async def test_second_model_changes_key(
        self, manager: AsyncIdempotencyCache
    ) -> None:
        calls = 0

        @idempotent()
        async def create(user: CurrentUser, body: TransferDto) -> int:
            nonlocal calls
            calls += 1
            return calls

        user = CurrentUser(name="alice")
        assert await create(user=user, body=TransferDto(amount=100, to="bob")) == 1
        assert await create(user=user, body=TransferDto(amount=999, to="bob")) == 2

    @pytest.mark.parametrize(
        ("first", "second"),
        [
            ("a", "b"),
            (1, 2),
            (1.5, 2.5),
            (True, False),
            (None, 0),
            (UUID(int=1), UUID(int=2)),
            (Decimal("1.10"), Decimal("1.20")),
            (datetime(2026, 10, 7, tzinfo=UTC), datetime(2026, 10, 8, tzinfo=UTC)),
            (Priority.LOW, Priority.HIGH),
            ([1, 2], [1, 3]),
            ({"page": 1}, {"page": 2}),
            ([TransferDto(amount=1, to="a")], [TransferDto(amount=2, to="a")]),
            (SecretStr("one"), SecretStr("two")),
            (SecretBytes(b"one"), SecretBytes(b"two")),
            (b"\xff\x01", b"\xff\x02"),
            ({"a"}, {"b"}),
            (frozenset({1}), frozenset({2})),
            ({1: "a"}, {"1": "a"}),
        ],
        ids=[
            "str",
            "int",
            "float",
            "bool",
            "none",
            "uuid",
            "decimal",
            "datetime",
            "enum",
            "list",
            "dict",
            "list-of-models",
            "secret-str",
            "secret-bytes",
            "bytes",
            "set",
            "frozenset",
            "int-key-dict",
        ],
    )
    async def test_plain_argument_value_changes_key(
        self, manager: AsyncIdempotencyCache, first: object, second: object
    ) -> None:
        calls = 0

        @idempotent()
        async def handle(body: TransferDto, value: object) -> int:
            nonlocal calls
            calls += 1
            return calls

        body = TransferDto(amount=1000, to="alice")
        assert await handle(body=body, value=first) == 1
        assert await handle(body=body, value=second) == 2
        assert await handle(body=body, value=first) == 1

    async def test_annotation_defined_after_decoration(
        self, manager: AsyncIdempotencyCache
    ) -> None:

        @idempotent()
        async def create(body: LateDto) -> int:
            return body.amount

        class LateDto(BaseModel):
            amount: int

        assert await create(body=LateDto(amount=7)) == 7
        assert len(manager._cache) == 1

    async def test_secret_field_changes_key(
        self, manager: AsyncIdempotencyCache
    ) -> None:
        calls = 0

        @idempotent()
        async def change_password(body: PasswordChangeDto) -> int:
            nonlocal calls
            calls += 1
            return calls

        first = PasswordChangeDto(new_password=SecretStr("old-secret"))
        second = PasswordChangeDto(new_password=SecretStr("new-secret"))
        assert await change_password(body=first) == 1
        assert await change_password(body=second) == 2
        assert await change_password(body=first) == 1

    async def test_equal_sets_share_key(self, manager: AsyncIdempotencyCache) -> None:
        calls = 0

        @idempotent()
        async def search(body: TransferDto, tags: set[int]) -> int:
            nonlocal calls
            calls += 1
            return calls

        first, second = {1, 9}, {9, 1}
        # Equal sets that iterate in different orders; only sorting makes one key.
        assert first == second
        assert list(first) != list(second)
        body = TransferDto(amount=1000, to="alice")
        assert await search(body=body, tags=first) == 1
        assert await search(body=body, tags=second) == 1

    async def test_list_of_models_alone_is_cached(
        self, manager: AsyncIdempotencyCache
    ) -> None:
        calls = 0

        @idempotent()
        async def create_many(items: list[TransferDto]) -> int:
            nonlocal calls
            calls += 1
            return calls

        items = [TransferDto(amount=1, to="a"), TransferDto(amount=2, to="b")]
        assert await create_many(items=items) == 1
        assert await create_many(items=list(items)) == 1
        assert await create_many(items=items[:1]) == 2

    async def test_exclude_applies_to_models_in_a_list(
        self, manager: AsyncIdempotencyCache
    ) -> None:
        calls = 0

        @idempotent(exclude={"memo"})
        async def create_many(items: list[TransferDto]) -> int:
            nonlocal calls
            calls += 1
            return calls

        assert await create_many(items=[TransferDto(amount=1, to="a", memo="x")]) == 1
        assert await create_many(items=[TransferDto(amount=1, to="a", memo="y")]) == 1
        assert calls == 1

    async def test_model_that_cannot_be_serialized_runs_uncached(
        self, manager: AsyncIdempotencyCache
    ) -> None:
        calls = 0

        @idempotent()
        async def upload(body: TransferDto, file: UploadDto) -> int:
            nonlocal calls
            calls += 1
            return calls

        body = TransferDto(amount=1000, to="alice")
        file = UploadDto(handle=Handle())
        assert await upload(body=body, file=file) == 1
        assert await upload(body=body, file=file) == 2
        assert manager._cache == {}

    async def test_default_value_is_part_of_key(
        self, manager: AsyncIdempotencyCache
    ) -> None:
        calls = 0

        @idempotent()
        async def list_page(body: TransferDto, page: int = 1) -> int:
            nonlocal calls
            calls += 1
            return calls

        body = TransferDto(amount=1000, to="alice")
        assert await list_page(body=body) == 1
        assert await list_page(body=body, page=1) == 1
        assert await list_page(body=body, page=2) == 2

    async def test_iterator_argument_reaches_function_intact(
        self, manager: AsyncIdempotencyCache
    ) -> None:

        @idempotent()
        async def bulk(body: TransferDto, items: Iterator[TransferDto]) -> list[int]:
            return [item.amount for item in items]

        body = TransferDto(amount=1000, to="alice")
        items = (TransferDto(amount=n, to="a") for n in (1, 2))
        assert await bulk(body, items) == [1, 2]

    async def test_framework_objects_are_ignored(
        self, manager: AsyncIdempotencyCache
    ) -> None:
        calls = 0

        @idempotent()
        async def create(body: TransferDto, tasks: BackgroundTasks) -> int:
            nonlocal calls
            calls += 1
            return calls

        body = TransferDto(amount=1000, to="alice")
        assert await create(body=body, tasks=BackgroundTasks()) == 1
        assert await create(body=body, tasks=BackgroundTasks()) == 1
        assert calls == 1

    async def test_concurrent_duplicate_raises_409(
        self, manager: AsyncIdempotencyCache
    ) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        @idempotent()
        async def create(body: TransferDto) -> str:
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()
            return "done"

        body = TransferDto(amount=1000, to="alice")
        first = asyncio.create_task(create(body=body))
        await started.wait()

        try:
            with pytest.raises(HTTPException) as exc:
                async with asyncio.timeout(1):
                    await create(body=body)
        finally:
            release.set()
        assert exc.value.status_code == 409
        assert await first == "done"
        assert calls == 1

    async def test_excluded_field_is_ignored_in_every_model(
        self, manager: AsyncIdempotencyCache
    ) -> None:
        calls = 0

        @idempotent(exclude={"memo"})
        async def create(user: CurrentUser, body: TransferDto) -> int:
            nonlocal calls
            calls += 1
            return calls

        alice = CurrentUser(name="alice", memo="x")
        body = TransferDto(amount=1000, to="bob", memo="a")
        assert await create(user=alice, body=body) == 1
        assert (
            await create(
                user=alice.model_copy(update={"memo": "y"}),
                body=body.model_copy(update={"memo": "b"}),
            )
            == 1
        )
        assert await create(user=CurrentUser(name="carol"), body=body) == 2

    async def test_without_model_argument_runs_every_time(
        self, manager: AsyncIdempotencyCache
    ) -> None:
        calls = 0

        @idempotent()
        async def ping(name: str) -> int:
            nonlocal calls
            calls += 1
            return calls

        assert await ping(name="a") == 1
        assert await ping(name="a") == 2
        assert manager._cache == {}
