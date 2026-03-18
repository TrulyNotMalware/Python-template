from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.pool import StaticPool

from app.core.config.config import LocalConfig
from app.core.db.session import (
    READING_ENGINE_NAME,
    WRITING_ENGINE_NAME,
    create_async_engine,
    engines,
    init_tables,
    reset_session_context,
    session,
    set_session_context,
)


@pytest.fixture(scope="session", autouse=True)
async def setup_db() -> None:
    config = LocalConfig()
    engine = create_async_engine(
        config.DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    engines[WRITING_ENGINE_NAME] = engine
    engines[READING_ENGINE_NAME] = engine
    await init_tables()


@pytest.fixture(autouse=True)
async def setup_session(setup_db: None) -> AsyncGenerator[None, Any]:
    session_id = str(uuid4())
    context = set_session_context(session_id=session_id)
    yield
    await session.remove()
    reset_session_context(context=context)
