import abc
from dataclasses import dataclass


class ErrorCode(abc.ABC):
    @abc.abstractmethod
    def get_status_code(self) -> int:
        raise NotImplementedError

    @abc.abstractmethod
    def get_message(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class ArgumentError:
    """One rejected argument, sent to the client as an item of ``detail``."""

    field_name: str
    value: str
    reason: str


class CustomException(Exception):
    def __init__(
        self,
        error_code: ErrorCode,
        argument_errors: list[ArgumentError] | None = None,
    ) -> None:
        super().__init__(error_code.get_message())
        self.code: int = error_code.get_status_code()
        self.message: str = error_code.get_message()
        self.argument_errors: list[ArgumentError] = (
            [] if argument_errors is None else list(argument_errors)
        )
