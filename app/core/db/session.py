from contextvars import ContextVar, Token
from typing import Any

from sqlalchemy import ClauseElement, Engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapper,
    Session,
)
from sqlalchemy.sql.expression import Delete, Insert, Update


class Base(DeclarativeBase):
    pass


session_context: ContextVar[str] = ContextVar("session_context")

WRITING_ENGINE_NAME: str = "writer"
READING_ENGINE_NAME: str = "reader"

# Lazy load
engines: dict[str, AsyncEngine] = {}


def get_session_context() -> str:
    return session_context.get()


def set_session_context(session_id: str) -> Token:
    return session_context.set(session_id)


def reset_session_context(context: Token) -> None:
    session_context.reset(context)


def init_engines(database_url: str) -> None:
    engines[WRITING_ENGINE_NAME] = create_async_engine(database_url, pool_recycle=3600)
    engines[READING_ENGINE_NAME] = create_async_engine(database_url, pool_recycle=3600)


async def init_tables() -> None:
    engine = engines.get(WRITING_ENGINE_NAME)

    if engine is None:
        raise RuntimeError("Engine not initialized. Call init_engines() first.")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


class RoutingSession(Session):
    def get_bind(
        self,
        mapper: Mapper[Any] | None = None,
        clause: ClauseElement | None = None,
        **kw: Any,
    ) -> Engine:
        if self._flushing or isinstance(clause, (Update, Delete, Insert)):
            return engines[WRITING_ENGINE_NAME].sync_engine
        return engines[READING_ENGINE_NAME].sync_engine


async_session_factory = async_sessionmaker(
    class_=AsyncSession,
    sync_session_class=RoutingSession,
)
session: async_scoped_session[AsyncSession] = async_scoped_session(
    session_factory=async_session_factory,
    scopefunc=get_session_context,
)
