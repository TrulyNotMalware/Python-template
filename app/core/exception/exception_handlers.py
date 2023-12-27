from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.exception.error_base import CustomException

"""
    Exception Handlers
"""


async def custom_exception_handler(request: Request, exc: CustomException):
    return JSONResponse(
        status_code=exc.code,
        content={"message": exc.message, "detail": exc.argument_errors}
    )