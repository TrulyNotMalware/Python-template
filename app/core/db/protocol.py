import abc
import enum
from dataclasses import dataclass
from typing import Any

from app.core.db.session import Base

type PrimaryKey = Any | tuple[Any, ...]


class SortOption(enum.StrEnum):
    ASC = "ASC"
    DESC = "DESC"


@dataclass(frozen=True, slots=True)
class Pageable:
    sort: str
    size: int
    page: int
    sort_option: SortOption = SortOption.DESC

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page must be greater than 0.")
        if self.size < 1:
            raise ValueError("size must be greater than 0.")
        if not isinstance(self.sort_option, SortOption):
            raise TypeError("sort_option must be a SortOption.")


class GenericRepository[T: Base](abc.ABC):
    @abc.abstractmethod
    async def find_by_pk(self, pk: PrimaryKey) -> T | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def find_by(self, **filters: Any) -> list[T]:
        raise NotImplementedError

    @abc.abstractmethod
    async def find_all(self, pageable: Pageable | None = None) -> list[T]:
        raise NotImplementedError

    @abc.abstractmethod
    async def save(self, entity: T) -> T:
        raise NotImplementedError

    @abc.abstractmethod
    async def update(self, entity: T) -> T:
        raise NotImplementedError

    @abc.abstractmethod
    async def update_from(self, pk: PrimaryKey, dto: object, exclude: list[str]) -> T:
        raise NotImplementedError

    @abc.abstractmethod
    async def delete_by_id(self, pk: PrimaryKey) -> None:
        raise NotImplementedError
