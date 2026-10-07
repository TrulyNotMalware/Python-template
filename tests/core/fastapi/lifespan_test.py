import asyncio
import subprocess
import sys
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.db.session import get_session_context
from app.core.utils.tasks import TaskOwner
from app.server import init_app
from app.user.model.user import UserRepository

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_server_module_registers_the_orm_tables() -> None:
    # A fresh interpreter: in this process other modules import the models anyway.
    code = (
        "import app.server\n"
        "from app.core.db.session import Base\n"
        "print(sorted(Base.metadata.tables))"
    )
    result = subprocess.run(  # noqa: S603  fixed arguments, current interpreter
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        cwd=PROJECT_ROOT,
    )

    assert "'users'" in result.stdout


def test_startup_creates_the_users_table(app: FastAPI) -> None:
    @app.get("/user-ids")
    async def user_ids(email: str) -> list[int]:
        users = await UserRepository().find_by(email=email)
        return [user.id for user in users]

    with TestClient(app) as client:
        response = client.get("/user-ids", params={"email": "nobody@example.com"})

    assert response.status_code == 200
    assert response.json() == []


def test_lifespan_state_exposes_task_owner_and_no_mongo_client(app: FastAPI) -> None:
    @app.get("/lifespan-state")
    async def lifespan_state(request: Request) -> dict[str, bool]:
        return {
            "has_task_owner": isinstance(request.state.tasks, TaskOwner),
            "mongo_is_none": request.state.mongo is None,
            "mongo_db_is_none": request.state.mongo_db is None,
        }

    with TestClient(app) as client:
        response = client.get("/lifespan-state")

    assert response.json() == {
        "has_task_owner": True,
        "mongo_is_none": True,
        "mongo_db_is_none": True,
    }


@pytest.mark.usefixtures("isolated_config")
@pytest.mark.parametrize("database", ["app_db", None])
def test_mongo_settings_expose_the_client_and_the_configured_database(
    monkeypatch: pytest.MonkeyPatch, database: str | None
) -> None:
    monkeypatch.setenv("ENV", "local")
    # The client connects lazily and no operation runs, so nothing has to
    # listen on this address.
    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:9/")
    if database is not None:
        monkeypatch.setenv("MONGO_DATABASE", database)
    app = init_app()

    @app.get("/mongo-state")
    async def mongo_state(request: Request) -> dict[str, object]:
        mongo_db = request.state.mongo_db
        return {
            "has_client": request.state.mongo is not None,
            "database": None if mongo_db is None else mongo_db.name,
            "same_client": mongo_db is None or mongo_db.client is request.state.mongo,
        }

    with TestClient(app) as client:
        response = client.get("/mongo-state")

    assert response.json() == {
        "has_client": True,
        "database": database,
        "same_client": True,
    }


def test_lifespan_runs_outside_a_session_scope(app: FastAPI) -> None:
    scopes: list[str | None] = []
    run_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def observed_lifespan(
        application: FastAPI,
    ) -> AsyncIterator[Mapping[str, Any]]:
        try:
            scopes.append(get_session_context())
        except LookupError:
            scopes.append(None)
        async with run_lifespan(application) as state:
            assert state is not None  # the application's lifespan yields its state
            yield state

    app.router.lifespan_context = observed_lifespan

    with TestClient(app):
        pass

    assert scopes == [None]


def test_shutdown_cancels_the_evict_task_before_the_loop_closes(
    app: FastAPI,
) -> None:
    # The test client cancels leftover tasks when its event loop closes, as
    # Ctrl+C does; under SIGTERM uvicorn does not. So the task state is read
    # right after the application's own shutdown code, on the still-running loop.
    evict_tasks: list[asyncio.Task[Any]] = []
    cancelled_by_shutdown: list[bool] = []
    run_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def observed_lifespan(
        application: FastAPI,
    ) -> AsyncIterator[Mapping[str, Any]]:
        async with run_lifespan(application) as state:
            assert state is not None  # the application's lifespan yields its state
            evict_tasks.extend(
                task
                for task in asyncio.all_tasks()
                if task.get_name() == "idempotency-evict"
            )
            yield state
        cancelled_by_shutdown.extend(task.cancelled() for task in evict_tasks)

    app.router.lifespan_context = observed_lifespan

    with TestClient(app):
        assert len(evict_tasks) == 1
        assert not evict_tasks[0].done()

    assert cancelled_by_shutdown == [True]
