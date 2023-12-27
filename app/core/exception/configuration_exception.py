from abc import ABC
from enum import Enum
from http import HTTPStatus
from typing import List

from app.core.exception.error_base import ErrorCode, ArgumentError, CustomException


class ConfigurationEnum(Enum):
    NOT_A_VALID_CONFIGURATION_NAME: tuple = (HTTPStatus.NOT_FOUND, "Configuration not found.")


class ConfigurationError(ErrorCode):
    def __init__(self, error: ConfigurationEnum):
        self.__value = error.value
        self.__http_status_code: HTTPStatus = self.__value[0]
        self.__message = self.__value[1]

    def get_status_code(self) -> int:
        return self.__http_status_code

    def get_message(self) -> str:
        return self.__message


class ConfigurationException(CustomException):
    def __init__(self, error_code: ErrorCode, argument_errors: List[ArgumentError] = None):
        super().__init__(error_code=error_code, argument_errors=argument_errors)