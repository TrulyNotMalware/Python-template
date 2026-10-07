from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config.config import ProdConfig, get_config
from app.server import init_app


@pytest.fixture
def isolated_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Make get_config() read only what the test sets.

    No settings variable from the shell and no .env file from the working
    directory reaches it, and the cached settings are dropped before and after.
    """
    monkeypatch.chdir(tmp_path)
    for name in ("ENV", *ProdConfig.model_fields):
        # setenv records the original state, unset included, so whatever the
        # code under test writes into os.environ is undone after the test.
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture
def app(isolated_config: None, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """A new application per test on LocalConfig (in-memory SQLite, no MongoDB)."""
    monkeypatch.setenv("ENV", "local")
    return init_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A client inside the application's lifespan: startup ran, shutdown runs after."""
    with TestClient(app) as client:
        yield client
