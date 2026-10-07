"""Exception handlers registered by the application factory."""

import dataclasses

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from fastapi.utils import is_body_allowed_for_status_code
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exception.error_base import CustomException


async def custom_exception_handler(
    request: Request, exc: CustomException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.code,
        content={
            "message": exc.message,
            "detail": [dataclasses.asdict(error) for error in exc.argument_errors],
        },
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> Response:
    # Registered on Starlette's class so the router's own 404 and 405 come here too.
    if not is_body_allowed_for_status_code(exc.status_code):
        return Response(status_code=exc.status_code, headers=exc.headers)
    return JSONResponse(
        {"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers
    )
