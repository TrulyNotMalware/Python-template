from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.server import init_app

DOC_PATHS = ("/swagger_ui", "/redoc", "/openapi.json")


def test_local_serves_api_docs(client: TestClient) -> None:
    for path in DOC_PATHS:
        assert client.get(path).status_code == 200, path


@pytest.mark.usefixtures("isolated_config")
def test_prod_closes_api_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("DATABASE_USER", "app")
    monkeypatch.setenv("DATABASE_PASSWORD", "unused")
    monkeypatch.setenv("DATABASE_HOST", "db.invalid")
    monkeypatch.setenv("DATABASE_PORT", "3306")
    monkeypatch.setenv("DATABASE_NAME", "service")
    # Without "with", the lifespan does not run, so nothing connects to MariaDB.
    client = TestClient(init_app())

    for path in DOC_PATHS:
        assert client.get(path).status_code == 404, path


@pytest.mark.usefixtures("isolated_config")
def test_env_in_an_env_file_does_not_close_api_docs() -> None:
    # isolated_config made the test's tmp_path the working directory.
    Path(".env.local").write_text("ENV=prod\n", encoding="utf-8")

    with TestClient(init_app()) as client:
        for path in DOC_PATHS:
            assert client.get(path).status_code == 200, path


@pytest.mark.usefixtures("isolated_config")
def test_wildcard_origin_is_allowed_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", '["*"]')

    with TestClient(init_app()) as client:
        response = client.get(
            "/openapi.json", headers={"Origin": "https://any.example"}
        )

    assert response.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.usefixtures("isolated_config")
def test_listed_origin_is_allowed_with_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", '["https://app.example.com"]')

    with TestClient(init_app()) as client:
        allowed = client.get(
            "/openapi.json", headers={"Origin": "https://app.example.com"}
        )
        other = client.get("/openapi.json", headers={"Origin": "https://evil.example"})

    assert allowed.headers["access-control-allow-origin"] == "https://app.example.com"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in other.headers
