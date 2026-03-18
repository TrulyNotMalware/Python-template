import abc


class ErrorCode(abc.ABC):
    @abc.abstractmethod
    def get_status_code(self) -> int:
        raise NotImplementedError

    @abc.abstractmethod
    def get_message(self) -> str:
        raise NotImplementedError


class ArgumentError:
    def __init__(self, field_name: str, value: str, reason: str) -> None:
        self.__field_name = field_name
        self.__value = value
        self.__reason = reason

    def get_field_name(self) -> str:
        return self.__field_name

    def get_value(self) -> str:
        return self.__value

    def get_reason(self) -> str:
        return self.__reason


class CustomException(Exception):
    def __init__(
        self,
        error_code: ErrorCode,
        argument_errors: list[ArgumentError] | None = None,
    ) -> None:
        self.code: int = error_code.get_status_code()
        self.message: str = error_code.get_message()
        self.argument_errors: list[ArgumentError] = argument_errors or []
