"""Async engines and the context-scoped session with writer/reader routing."""

from contextvars import ContextVar, Token
from typing import Any, override

from sqlalchemy import ClauseElement, Connection, Engine, event, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapper,
    ORMExecuteState,
    Session,
    SessionTransaction,
    UOWTransaction,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.expression import Delete, Insert, Update


class Base(DeclarativeBase):
    pass


session_context: ContextVar[str] = ContextVar("session_context")

WRITING_ENGINE_NAME: str = "writer"
READING_ENGINE_NAME: str = "reader"

_ROUTED_TO_WRITER = "routed_to_writer"

# Filled by init_engines() from the application lifespan, never at import time.
engines: dict[str, AsyncEngine] = {}


def get_session_context() -> str:
    return session_context.get()


def set_session_context(session_id: str) -> Token[str]:
    return session_context.set(session_id)


def reset_session_context(context: Token[str]) -> None:
    session_context.reset(context)


def _is_sqlite_memory(url: str) -> bool:
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        return False
    return (
        parsed.database in (None, "", ":memory:")
        or parsed.query.get("mode") == "memory"
    )


def _create_engine(url: str) -> AsyncEngine:
    if _is_sqlite_memory(url):
        # An in-memory SQLite database lives in one connection, so every session
        # has to share that connection. A file database must not: one session's
        # rollback would discard another session's flushed rows.
        return create_async_engine(
            url,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    return create_async_engine(url, pool_recycle=3600)


def init_engines(database_url: str, read_url: str | None = None) -> None:
    """Create the writer engine and, for a distinct ``read_url``, a reader engine.

    Without a separate read URL both names map to the same engine object.
    """
    writer = _create_engine(database_url)
    if read_url is None or read_url == database_url:
        reader = writer
    else:
        reader = _create_engine(read_url)
    engines[WRITING_ENGINE_NAME] = writer
    engines[READING_ENGINE_NAME] = reader


async def dispose_engines() -> None:
    disposing = set(engines.values())
    engines.clear()
    for engine in disposing:
        await engine.dispose()


def _get_engine(name: str) -> AsyncEngine:
    engine = engines.get(name)
    if engine is None:
        raise RuntimeError("Engine not initialized. Call init_engines() first.")
    return engine


async def init_tables() -> None:
    async with _get_engine(WRITING_ENGINE_NAME).begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


class RoutingSession(Session):
    """Route writes to the writer engine and plain reads to the reader engine.

    Once the session has flushed or executed an INSERT, UPDATE or DELETE
    statement, every statement goes to the writer until the outermost
    transaction ends, so a read (``refresh()`` included) sees the session's own
    uncommitted writes.

    ``select(...).with_for_update()`` and DML written as ``text()`` are not
    recognized and go to the reader. With a read replica configured, call
    ``use_writer()`` before them so the lock or the write lands on the primary.
    """

    @override
    def get_bind[O](
        self,
        mapper: type[O] | Mapper[O] | None = None,
        *,
        clause: ClauseElement | None = None,
        bind: Engine | Connection | None = None,
        _sa_skip_events: bool | None = None,
        _sa_skip_for_implicit_returning: bool = False,
        **kw: Any,
    ) -> Engine | Connection:
        if bind is not None:
            return bind
        if isinstance(clause, (Update, Delete, Insert)):
            # Core and bulk DML do not flush, so mark the session here as well.
            self.info[_ROUTED_TO_WRITER] = True
            return _get_engine(WRITING_ENGINE_NAME).sync_engine
        if self._flushing or self.info.get(_ROUTED_TO_WRITER, False):
            return _get_engine(WRITING_ENGINE_NAME).sync_engine
        return _get_engine(READING_ENGINE_NAME).sync_engine


@event.listens_for(RoutingSession, "after_flush")
def _route_to_writer_after_flush(
    session: Session, flush_context: UOWTransaction
) -> None:
    session.info[_ROUTED_TO_WRITER] = True


@event.listens_for(RoutingSession, "do_orm_execute")
def _route_to_writer_for_orm_dml(orm_execute_state: ORMExecuteState) -> None:
    # ORM UPDATE/DELETE with synchronize_session="fetch" runs a SELECT before the
    # statement reaches get_bind() on backends without UPDATE ... RETURNING.
    if orm_execute_state.is_update or orm_execute_state.is_delete:
        orm_execute_state.session.info[_ROUTED_TO_WRITER] = True


@event.listens_for(RoutingSession, "after_transaction_end")
def _reset_routing_after_transaction(
    session: Session, transaction: SessionTransaction
) -> None:
    if transaction.parent is None:
        session.info.pop(_ROUTED_TO_WRITER, None)


async_session_factory = async_sessionmaker(
    class_=AsyncSession,
    sync_session_class=RoutingSession,
    expire_on_commit=False,
)
session: async_scoped_session[AsyncSession] = async_scoped_session(
    session_factory=async_session_factory,
    scopefunc=get_session_context,
)


def use_writer() -> None:
    """Send the rest of the current transaction of this context's session to the writer.

    Call it before ``SELECT ... FOR UPDATE`` or ``text()`` DML, which the routing
    cannot recognize. It applies until the outermost transaction ends.
    """
    try:
        current = session()
    except LookupError as exc:
        raise RuntimeError(
            "use_writer() requires an active session scope "
            "(set_session_context / SQLAlchemyMiddleware / standalone_session)"
        ) from exc
    current.info[_ROUTED_TO_WRITER] = True
