import logging
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

LOGGER_NAME = "app.core.fastapi.middlewares.response_log"
# The PNG signature starts with 0x89, which is not valid UTF-8.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + bytes(range(256))
KOREAN_TEXT = "안녕하세요, 세계"


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    @app.get("/png")
    async def png() -> Response:
        return Response(content=PNG_BYTES, media_type="image/png")

    @app.get("/korean")
    async def korean() -> StreamingResponse:
        encoded = KOREAN_TEXT.encode()

        async def two_chunks() -> AsyncIterator[bytes]:
            # Each Hangul syllable is 3 bytes: byte 4 is inside the second one.
            yield encoded[:4]
            yield encoded[4:]

        return StreamingResponse(two_chunks(), media_type="text/plain; charset=utf-8")

    @app.get("/broken")
    async def broken() -> Response:
        raise RuntimeError("handler failed")

    return app


@pytest.fixture
def response_log(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    return caplog


def test_binary_body_passes_through_unchanged(
    client: TestClient, response_log: pytest.LogCaptureFixture
) -> None:
    response = client.get("/png")

    assert response.status_code == 200
    assert response.content == PNG_BYTES
    assert f"GET /png -> 200 ({len(PNG_BYTES)} bytes)" in response_log.messages


def test_multibyte_text_split_across_chunks_passes_through(
    client: TestClient, response_log: pytest.LogCaptureFixture
) -> None:
    response = client.get("/korean")

    assert response.status_code == 200
    assert response.text == KOREAN_TEXT
    size = len(KOREAN_TEXT.encode())
    assert f"GET /korean -> 200 ({size} bytes)" in response_log.messages


def test_request_whose_handler_raised_is_still_logged(
    app: FastAPI, response_log: pytest.LogCaptureFixture
) -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/broken")

    assert response.status_code == 500
    assert "GET /broken -> unhandled (0 bytes)" in response_log.messages


def test_log_line_has_no_headers_or_body(
    client: TestClient, response_log: pytest.LogCaptureFixture
) -> None:
    client.get("/korean", headers={"Authorization": "Bearer secret-token"})

    logged = "\n".join(response_log.messages)
    assert "secret-token" not in logged
    assert KOREAN_TEXT not in logged
