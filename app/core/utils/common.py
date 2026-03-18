import abc
import enum
import logging
from typing import Any, Literal, TypeVar

from sqlalchemy import Result, Select, and_, select
from sqlalchemy.ext.asyncio import async_scoped_session
from sqlalchemy.inspection import Inspectable, inspect
from sqlalchemy.orm import Mapper
from sqlalchemy.sql import roles
from sqlalchemy.sql._typing import _HasClauseElement
from sqlalchemy.sql.elements import SQLCoreOperations

from app.core.db import Base

logger = logging.getLogger(__name__)


class Singleton(type):
    """Return a object that can be used as a singleton"""

    _instances: dict[type, Any] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            logger.info(f"Singleton Instance {cls.__name__} Not found. create.")
            cls._instances[cls] = super().__call__(*args, **kwargs)
        logger.info(f"Return Singleton instance {cls.__name__}")
        return cls._instances[cls]


# Type definitions for SQLAlchemy interface
_T = TypeVar("_T")
_O = TypeVar("_O", bound=object)
T = TypeVar("T", bound=Base)

_PKIdentityArgument = Any | tuple[Any, ...]
_EntityBindKey = type[_O] | Mapper[_O]
_ColumnsClauseArgument = (
    roles.TypedColumnsClauseRole[_T]
    | roles.ColumnsClauseRole
    | SQLCoreOperations[_T]
    | Literal["*", 1]
    | type[_T]
    | Inspectable[_HasClauseElement]
    | _HasClauseElement
)


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


class SQLRepository[T: Base](GenericRepository[T], abc.ABC):
    def __init__(self, session: async_scoped_session[Any], entity: type[T]) -> None:
        self._session = session
        self._entity = entity

    def __find_by_pk(self, pk: _PKIdentityArgument) -> Select[Any]:
        inspector = inspect(self._entity)
        return select(self._entity).where(inspector.primary_key[0] == pk)

    async def find_by_pk(self, pk: _PKIdentityArgument) -> T | None:
        result: Result[Any] = await self._session.execute(self.__find_by_pk(pk=pk))
        return result.scalars().first()

    def __find_many(self, **filters: Any) -> Select[Any]:
        base = select(self._entity)
        where_case = []
        for key, value in filters.items():
            if not hasattr(self._entity, key):
                raise ValueError(f"Invalid Column name {key}.")
            where_case.append(getattr(self._entity, key) == value)
        if not where_case:
            return base
        if len(where_case) == 1:
            return base.where(where_case[0])
        return base.where(and_(*where_case))

    async def find_by(self, **filters: Any) -> list[T]:
        result: Result[Any] = await self._session.execute(self.__find_many(**filters))
        return list(result.scalars().all())

    async def find_all(self, pageable: Pageable | None = None) -> list[T]:
        query = select(self._entity)
        if pageable is not None:
            column = getattr(self._entity, pageable.sort, None)
            if column is None:
                raise ValueError(f"Invalid sort column: {pageable.sort}")

            order = column.desc() if pageable.sort_option == "DESC" else column.asc()
            query = query.order_by(order)

            offset = (pageable.page - 1) * pageable.size
            query = query.offset(offset).limit(pageable.size)

        result: Result[Any] = await self._session.execute(query)
        return list(result.scalars().all())

    async def save(self, entity: T) -> T:
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def update(self, record: T) -> T:
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return record

    async def delete_by_id(self, pk: _PKIdentityArgument) -> None:
        record = await self.find_by_pk(pk=pk)
        if record is not None:
            await self._session.delete(record)
            await self._session.flush()

    async def update_from(
        self, pk: _PKIdentityArgument, dto: Any, exclude: list[str]
    ) -> T:
        exclude_set: set[str] = set(exclude)
        entity: T | None = await self.find_by_pk(pk=pk)
        if entity is None:
            raise ValueError(f"Entity {pk} not found")

        mapper = inspect(self._entity)
        pk_columns = {col.name for col in mapper.primary_key}

        for attr in mapper.attrs:
            col_name = attr.key
            if col_name in pk_columns or col_name in exclude_set:
                continue
            set_value = getattr(dto, col_name, None)
            if set_value is not None:
                setattr(entity, col_name, set_value)

        return await self.update(record=entity)
