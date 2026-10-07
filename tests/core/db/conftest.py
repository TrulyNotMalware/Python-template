from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

import app.user.model.user  # noqa: F401  registers the users table on Base.metadata
from app.core.db.session import (
    WRITING_ENGINE_NAME,
    Base,
    dispose_engines,
    engines,
    init_engines,
    init_tables,
    reset_session_context,
    session,
    set_session_context,
)


@pytest.fixture(scope="session")
async def db_engines() -> AsyncIterator[dict[str, AsyncEngine]]:
    init_engines("sqlite+aiosqlite://")
    await init_tables()
    created = dict(engines)
    yield created
    # Another fixture or an application lifespan may have replaced the engines.
    engines.clear()
    engines.update(created)
    await dispose_engines()


@pytest.fixture
async def session_id(db_engines: dict[str, AsyncEngine]) -> AsyncIterator[str]:
    """Give the test its own session scope; the session is closed afterwards."""
    # An application lifespan in another test calls init_engines() and
    # dispose_engines(), which replace or empty the global registry.
    engines.clear()
    engines.update(db_engines)
    session_id = str(uuid4())
    context = set_session_context(session_id=session_id)
    yield session_id
    await session.remove()
    reset_session_context(context=context)
    # Tests that commit leave rows behind in the shared in-memory database.
    async with db_engines[WRITING_ENGINE_NAME].begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            await connection.execute(table.delete())
