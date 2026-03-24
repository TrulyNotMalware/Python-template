import abc
import enum
import logging
from typing import Any

from app.core.db import Base

logger = logging.getLogger(__name__)


_PKIdentityArgument = Any | tuple[Any, ...]


class SortOption(enum.StrEnum):
    ASC = "ASC"
    DESC = "DESC"


class Pageable:
    def __init__(
        self,
        sort: str,
        size: int,
        page: int,
        sort_option: SortOption = SortOption.DESC,
    ) -> None:
        if page < 1:
            raise ValueError("page must be greater than 0.")
        if size < 1:
            raise ValueError("size must be greater than 0.")
        if sort_option not in ("ASC", "DESC"):
            raise ValueError("sort option must be ASC or DESC.")
        self.sort = sort
        self.sort_option = sort_option
        self.size = size
        self.page = page


class GenericRepository[T: Base](abc.ABC):
    @abc.abstractmethod
    async def find_by_pk(self, pk: _PKIdentityArgument) -> T | None:
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
    async def update_from(
        self, pk: _PKIdentityArgument, dto: Any, exclude: list[str]
    ) -> T:
        raise NotImplementedError

    @abc.abstractmethod
    async def delete_by_id(self, pk: _PKIdentityArgument) -> None:
        raise NotImplementedError
