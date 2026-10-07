import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.exception.configuration_exception import (
    ConfigurationEnum,
    ConfigurationError,
    ConfigurationException,
)
from app.core.exception.error_base import ArgumentError


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    @app.get("/configuration-error")
    async def configuration_error() -> None:
        raise ConfigurationException(
            error_code=ConfigurationError(
                error=ConfigurationEnum.NOT_A_VALID_CONFIGURATION_NAME
            ),
            argument_errors=[
                ArgumentError(
                    field_name="env",
                    value="qa",
                    reason="env type qa is not supported",
                )
            ],
        )

    @app.get("/configuration-error-without-arguments")
    async def configuration_error_without_arguments() -> None:
        raise ConfigurationException(
            error_code=ConfigurationError(
                error=ConfigurationEnum.NOT_A_VALID_CONFIGURATION_NAME
            )
        )

    @app.get("/no-content")
    async def no_content() -> None:
        raise HTTPException(status_code=204)

    @app.get("/rate-limited")
    async def rate_limited() -> None:
        raise HTTPException(
            status_code=429, detail="slow down", headers={"Retry-After": "1"}
        )

    return app


def test_custom_exception_is_sent_as_json(client: TestClient) -> None:
    response = client.get("/configuration-error")

    assert response.status_code == 404
    body = response.json()
    assert body["message"] == "Configuration not found."
    assert body["detail"][0]["field_name"] == "env"
    assert body["detail"] == [
        {
            "field_name": "env",
            "value": "qa",
            "reason": "env type qa is not supported",
        }
    ]


def test_custom_exception_without_argument_errors_has_empty_detail(
    client: TestClient,
) -> None:
    response = client.get("/configuration-error-without-arguments")

    assert response.status_code == 404
    assert response.json() == {"message": "Configuration not found.", "detail": []}


def test_router_not_found_keeps_detail_shape(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_http_exception_without_body_status_sends_empty_body(
    client: TestClient,
) -> None:
    response = client.get("/no-content")

    assert response.status_code == 204
    assert response.content == b""


def test_http_exception_headers_are_forwarded(client: TestClient) -> None:
    response = client.get("/rate-limited")

    assert response.status_code == 429
    assert response.json() == {"detail": "slow down"}
    assert response.headers["retry-after"] == "1"
