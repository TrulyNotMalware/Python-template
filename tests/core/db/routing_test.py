import contextvars
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Connection, insert, select, update
from sqlalchemy.engine.interfaces import DBAPICursor, ExecutionContext
from sqlalchemy.event import listen, remove
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import (
    READING_ENGINE_NAME,
    WRITING_ENGINE_NAME,
    Base,
    dispose_engines,
    engines,
    init_engines,
    init_tables,
    reset_session_context,
    session,
    set_session_context,
    use_writer,
)
from app.user.model.user import User, UserRepository


@dataclass
class StatementLog:
    writer: list[str] = field(default_factory=list)
    reader: list[str] = field(default_factory=list)

    def clear(self) -> None:
        self.writer.clear()
        self.reader.clear()


def _recorder(statements: list[str]) -> Callable[..., None]:
    def record(
        conn: Connection,
        cursor: DBAPICursor,
        statement: str,
        parameters: Any,
        context: ExecutionContext | None,
        executemany: bool,
    ) -> None:
        statements.append(statement.split(maxsplit=1)[0].upper())

    return record


@pytest.fixture
async def file_engines(
    tmp_path: Path, session_id: str
) -> AsyncIterator[tuple[AsyncEngine, AsyncEngine]]:
    """Writer and reader as two engines on one SQLite file, like a primary/replica pair.

    The reader's connection cannot see what the writer has flushed but not
    committed, which is what a replica cannot see either.
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'routing.db'}"
    writer = create_async_engine(url)
    reader = create_async_engine(url)
    async with writer.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    previous = dict(engines)
    engines[WRITING_ENGINE_NAME] = writer
    engines[READING_ENGINE_NAME] = reader
    try:
        yield writer, reader
    finally:
        await session.remove()
        engines.clear()
        engines.update(previous)
        await writer.dispose()
        await reader.dispose()


@pytest.fixture
def statements(
    file_engines: tuple[AsyncEngine, AsyncEngine],
) -> Iterator[StatementLog]:
    writer, reader = file_engines
    log = StatementLog()
    on_writer = _recorder(log.writer)
    on_reader = _recorder(log.reader)
    listen(writer.sync_engine, "before_cursor_execute", on_writer)
    listen(reader.sync_engine, "before_cursor_execute", on_reader)
    yield log
    remove(writer.sync_engine, "before_cursor_execute", on_writer)
    remove(reader.sync_engine, "before_cursor_execute", on_reader)


def _user(name: str) -> User:
    return User(password="pw", email=f"{name}@example.com", nickname=name)


async def _seed_committed_user(engine: AsyncEngine, name: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            insert(User).values(
                password="pw", email=f"{name}@example.com", nickname=name
            )
        )


async def test_plain_select_goes_to_reader(statements: StatementLog) -> None:
    await UserRepository().find_by(nickname="nobody")

    assert statements.reader == ["SELECT"]
    assert statements.writer == []


async def test_save_refreshes_through_writer(statements: StatementLog) -> None:
    saved = await UserRepository().save(_user("alice"))

    assert saved.id is not None
    assert saved.is_admin is False
    assert statements.writer == ["INSERT", "SELECT"]
    assert statements.reader == []


async def test_reads_after_flush_see_uncommitted_rows(
    statements: StatementLog,
) -> None:
    repository = UserRepository()
    await repository.find_by(nickname="alice")
    await repository.save(_user("alice"))
    statements.clear()

    found = await repository.find_by(nickname="alice")

    assert [user.nickname for user in found] == ["alice"]
    assert statements.writer == ["SELECT"]
    assert statements.reader == []


async def test_reads_return_to_reader_after_commit(statements: StatementLog) -> None:
    repository = UserRepository()
    await repository.save(_user("alice"))
    await session.commit()
    statements.clear()

    found = await repository.find_by(nickname="alice")

    assert [user.nickname for user in found] == ["alice"]
    assert statements.reader == ["SELECT"]
    assert statements.writer == []


async def test_reads_return_to_reader_after_rollback(
    statements: StatementLog,
) -> None:
    repository = UserRepository()
    await repository.save(_user("alice"))
    await session.rollback()
    statements.clear()

    assert await repository.find_by(nickname="alice") == []
    assert statements.reader == ["SELECT"]


async def test_core_update_goes_to_writer(statements: StatementLog) -> None:
    await session.execute(
        update(User).where(User.nickname == "nobody").values(is_admin=True)
    )

    assert statements.writer == ["UPDATE"]
    assert statements.reader == []


async def test_core_update_routes_the_next_read_to_writer(
    file_engines: tuple[AsyncEngine, AsyncEngine], statements: StatementLog
) -> None:
    writer, _ = file_engines
    await _seed_committed_user(writer, "alice")
    statements.clear()

    await session.execute(
        update(User).where(User.nickname == "alice").values(nickname="renamed")
    )
    found = await UserRepository().find_by(nickname="renamed")

    assert [user.nickname for user in found] == ["renamed"]
    assert statements.writer == ["UPDATE", "SELECT"]
    assert statements.reader == []


async def test_for_update_select_goes_to_reader_without_use_writer(
    statements: StatementLog,
) -> None:
    # Known limitation: the routing cannot see with_for_update().
    await session.execute(select(User).with_for_update())

    assert statements.reader == ["SELECT"]
    assert statements.writer == []


async def test_use_writer_pins_the_transaction_to_writer(
    statements: StatementLog,
) -> None:
    await UserRepository().find_by(nickname="nobody")
    statements.clear()

    use_writer()
    await session.execute(select(User).with_for_update())
    assert statements.writer == ["SELECT"]
    assert statements.reader == []

    await session.commit()
    statements.clear()
    await UserRepository().find_by(nickname="nobody")
    assert statements.reader == ["SELECT"]
    assert statements.writer == []


def test_use_writer_outside_a_session_scope_raises() -> None:
    with pytest.raises(RuntimeError, match="requires an active session scope") as info:
        contextvars.Context().run(use_writer)

    assert isinstance(info.value.__cause__, LookupError)


async def test_fetch_synchronization_selects_from_writer(
    file_engines: tuple[AsyncEngine, AsyncEngine], statements: StatementLog
) -> None:
    writer, reader = file_engines
    for engine in (writer, reader):
        engine.sync_engine.dialect.update_returning = False  # like MariaDB
    await _seed_committed_user(writer, "alice")
    statements.clear()

    await session.execute(
        update(User).where(User.nickname == "alice").values(nickname="renamed"),
        execution_options={"synchronize_session": "fetch"},
    )

    assert statements.writer == ["SELECT", "UPDATE"]
    assert statements.reader == []


async def test_init_engines_treats_mode_memory_uri_as_in_memory(
    monkeypatch: pytest.MonkeyPatch, session_id: str
) -> None:
    created: list[dict[str, Any]] = []

    def spy(url: str, **kwargs: Any) -> AsyncEngine:
        created.append(kwargs)
        return create_async_engine(url, **kwargs)

    monkeypatch.setattr("app.core.db.session.create_async_engine", spy)
    previous = dict(engines)
    init_engines(
        f"sqlite+aiosqlite:///file:{uuid4().hex}?mode=memory&cache=shared&uri=true"
    )
    try:
        await init_tables()
        assert await UserRepository().find_all() == []
    finally:
        await session.remove()
        await dispose_engines()
        engines.clear()
        engines.update(previous)

    assert len(created) == 1
    assert created[0]["poolclass"] is StaticPool
    assert "pool_recycle" not in created[0]


async def test_init_engines_shares_one_engine_without_read_url(
    session_id: str,
) -> None:
    previous = dict(engines)
    try:
        init_engines("sqlite+aiosqlite://")
        assert engines[WRITING_ENGINE_NAME] is engines[READING_ENGINE_NAME]
        assert isinstance(engines[WRITING_ENGINE_NAME].pool, StaticPool)

        init_engines("sqlite+aiosqlite://", "sqlite+aiosqlite://")
        assert engines[WRITING_ENGINE_NAME] is engines[READING_ENGINE_NAME]

        init_engines("sqlite+aiosqlite:///:memory:")
        assert isinstance(engines[WRITING_ENGINE_NAME].pool, StaticPool)
        await dispose_engines()
        assert engines == {}
    finally:
        engines.clear()
        engines.update(previous)


async def test_init_engines_creates_reader_for_distinct_read_url(
    tmp_path: Path, session_id: str
) -> None:
    previous = dict(engines)
    try:
        init_engines(
            f"sqlite+aiosqlite:///{tmp_path / 'primary.db'}",
            f"sqlite+aiosqlite:///{tmp_path / 'replica.db'}",
        )
        assert engines[WRITING_ENGINE_NAME] is not engines[READING_ENGINE_NAME]
        assert not isinstance(engines[WRITING_ENGINE_NAME].pool, StaticPool)
        assert not isinstance(engines[READING_ENGINE_NAME].pool, StaticPool)
        await dispose_engines()
    finally:
        engines.clear()
        engines.update(previous)


async def test_file_database_sessions_do_not_share_a_connection(
    tmp_path: Path, session_id: str
) -> None:
    previous = dict(engines)
    init_engines(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    try:
        await init_tables()
        first = set_session_context(session_id=str(uuid4()))
        session.add(_user("alice"))
        await session.flush()

        second = set_session_context(session_id=str(uuid4()))
        await UserRepository().find_by(nickname="nobody")
        await session.remove()  # this request ends with a rollback
        reset_session_context(context=second)

        await session.commit()  # the first request commits its flushed row
        await session.remove()
        reset_session_context(context=first)

        nicknames = [user.nickname for user in await UserRepository().find_all()]
    finally:
        await session.remove()
        await dispose_engines()
        engines.clear()
        engines.update(previous)

    assert nicknames == ["alice"]
