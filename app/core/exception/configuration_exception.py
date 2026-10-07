from enum import Enum
from http import HTTPStatus

from app.core.exception.error_base import ArgumentError, CustomException, ErrorCode


class ConfigurationEnum(Enum):
    NOT_A_VALID_CONFIGURATION_NAME = (
        HTTPStatus.NOT_FOUND,
        "Configuration not found.",
    )


class ConfigurationError(ErrorCode):
    def __init__(self, error: ConfigurationEnum) -> None:
        status_code, message = error.value
        self._status_code: int = status_code
        self._message: str = message

    def get_status_code(self) -> int:
        return self._status_code

    def get_message(self) -> str:
        return self._message


class ConfigurationException(CustomException):
    def __init__(
        self,
        error_code: ErrorCode,
        argument_errors: list[ArgumentError] | None = None,
    ) -> None:
        super().__init__(error_code=error_code, argument_errors=argument_errors)
