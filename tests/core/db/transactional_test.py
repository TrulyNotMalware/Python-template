import asyncio
from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy.event import listen, remove
from sqlalchemy.orm import Session

from app.core.db import Transactional, standalone_session
from app.core.db.session import reset_session_context, session, set_session_context
from app.user.model.user import User, UserRepository


class Boom(Exception):
    pass


def _user(name: str) -> User:
    return User(password="pw", email=f"{name}@example.com", nickname=name)


async def _nicknames_in_new_session() -> list[str]:
    """Close the test's session, rolling back what it did not commit, then read."""
    await session.remove()
    context = set_session_context(session_id=str(uuid4()))
    try:
        return [user.nickname for user in await UserRepository().find_all()]
    finally:
        await session.remove()
        reset_session_context(context=context)


@pytest.fixture
def commits(session_id: str) -> Iterator[list[Session]]:
    committed: list[Session] = []

    def record(sync_session: Session) -> None:
        committed.append(sync_session)

    sync_session = session().sync_session
    listen(sync_session, "after_commit", record)
    yield committed
    remove(sync_session, "after_commit", record)


@Transactional()
async def save_user(name: str) -> User:
    return await UserRepository().save(_user(name))


@Transactional()
async def save_two_users(first: str, second: str) -> list[User]:
    return [await save_user(first), await save_user(second)]


@Transactional()
async def save_user_then_fail(name: str) -> None:
    await UserRepository().save(_user(name))
    raise Boom(name)


@Transactional()
async def save_user_then_fail_in_nested_call(first: str, second: str) -> None:
    await save_user(first)
    await save_user_then_fail(second)


async def test_commits_after_an_earlier_read(commits: list[Session]) -> None:
    await UserRepository().find_by(nickname="alice")  # autobegins a transaction

    await save_user("alice")

    assert len(commits) == 1
    assert await _nicknames_in_new_session() == ["alice"]


async def test_nested_calls_commit_once(commits: list[Session]) -> None:
    users = await save_two_users("alice", "bob")

    assert [user.nickname for user in users] == ["alice", "bob"]
    assert len(commits) == 1
    assert sorted(await _nicknames_in_new_session()) == ["alice", "bob"]


async def test_rolls_back_when_the_call_raises(commits: list[Session]) -> None:
    with pytest.raises(Boom, match="alice"):
        await save_user_then_fail("alice")

    assert commits == []
    assert await UserRepository().find_by(nickname="alice") == []
    assert await _nicknames_in_new_session() == []


async def test_nested_failure_rolls_back_the_outer_call(
    commits: list[Session],
) -> None:
    with pytest.raises(Boom, match="bob"):
        await save_user_then_fail_in_nested_call("alice", "bob")

    assert commits == []
    assert await _nicknames_in_new_session() == []


async def test_returned_entity_is_readable_after_commit(session_id: str) -> None:
    user = await save_user("alice")

    assert user.id is not None
    assert user.nickname == "alice"
    assert user.is_admin is False


async def test_decorated_call_runs_as_a_task(session_id: str) -> None:
    user = await asyncio.create_task(save_user("alice"))

    assert user.nickname == "alice"
    assert await _nicknames_in_new_session() == ["alice"]


async def test_session_is_reusable_after_a_failed_call(session_id: str) -> None:
    with pytest.raises(Boom):
        await save_user_then_fail("alice")

    user = await save_user("alice")

    assert user.nickname == "alice"
    assert await _nicknames_in_new_session() == ["alice"]


async def test_standalone_session_runs_in_its_own_scope(session_id: str) -> None:
    outer = session()

    @standalone_session
    async def create(name: str) -> tuple[int, bool]:
        user = await save_user(name)
        return user.id, session() is outer

    user_id, shared = await create("alice")

    assert shared is False
    assert session() is outer
    found = await UserRepository().find_by_pk(pk=user_id)
    assert found is not None
    assert found.nickname == "alice"
