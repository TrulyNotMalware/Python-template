import abc
import logging
from typing import TypeVar, Any, Union, Type, Literal, Tuple, Generic, Optional, List

from sqlalchemy.ext.asyncio import async_scoped_session
from sqlalchemy.inspection import Inspectable, inspect
from sqlalchemy.sql import roles
from sqlalchemy.sql._typing import _HasClauseElement
from sqlalchemy import Select, and_, select, Result

from app.core.db import Base

logger = logging.getLogger(__name__)

class Singleton(type):
    _instances = dict()
    """
    Return a object that can be used as a singleton
    """

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            logger.info(f"Singleton Instance {cls.__name__} Not found. create.")
            cls._instances[cls] = super().__call__(*args, **kwargs)
        logger.info(f"Return Singleton instance {cls.__name__}")
        return cls._instances[cls]


"""
Type definitions for SQLAlchemy interface
"""
_T = TypeVar("_T", bound=Any)  # Type variable.
_O = TypeVar("_O", bound=object)  # Object Type
T = TypeVar("T", bound=Base)

_PKIdentityArgument = Union[Any, Tuple[Any, ...]]
_EntityBindKey = Union[Type[_O], "Mapper[_O]"]
_ColumnsClauseArgument = Union[
    roles.TypedColumnsClauseRole[_T],
    roles.ColumnsClauseRole,
    "SQLCoreOperations[_T]",
    Literal["*", 1],
    Type[_T],
    Inspectable[_HasClauseElement],
    _HasClauseElement,
]


class Pageable:
    def __init__(self, sort: str, size: int, page: int,
                 sort_option: str = "DESC",):
        self.sort = sort
        self.sort_option = sort_option
        self.size = size
        self.page = page


class GenericRepository(Generic[T], abc.ABC):
    @abc.abstractmethod
    async def find_by_id(self, id: _PKIdentityArgument) -> Optional[T]:
        raise NotImplementedError()

    @abc.abstractmethod
    async def find_by(self, **filters) -> List[T]:
        raise NotImplementedError()

    @abc.abstractmethod
    async def find_all(self, pageable: Pageable = None) -> List[T]:
        raise NotImplementedError()

    @abc.abstractmethod
    async def save(self, entity: T) -> T:
        raise NotImplementedError()

    @abc.abstractmethod
    async def update(self, entity: T) -> T:
        raise NotImplementedError()

    @abc.abstractmethod
    async def update_from(self, id: _PKIdentityArgument, dto, exclude: dict) -> T:
        raise NotImplementedError()

    @abc.abstractmethod
    async def delete_by_id(self, entity: T) -> None:
        raise NotImplementedError()


class SQLRepository(GenericRepository[T], abc.ABC):
    def __init__(self, session: async_scoped_session, entity: Type[T]):
        self._session: async_scoped_session = session
        self._entity = entity

    def __find_by_id(self, id: _PKIdentityArgument) -> Select[Any]:
        inspector = inspect(self._entity)
        return select(self._entity).where(inspector.primary_key[0] == id)

    async def find_by_id(self, id: _PKIdentityArgument) -> Optional[T]:
        result: Result[Any] = await self._session.execute(self.__find_by_id(id=id))
        return result.scalars().first()

    def __find_many(self, **filters):
        base = select(self._entity)
        where_case = list()
        for key, value in filters.items():

            if not hasattr(self._entity, key):
                raise ValueError(f"Invalid Column name {key}.")
            where_case.append(getattr(self._entity, key) == value)
        if len(where_case) == 1:
            return base.where(where_case[0])

        elif len(where_case) > 1:
            return base.where(and_(*where_case))

    async def find_by(self, **filters) -> List[T]:
        result: Result[Any] = await self._session.execute(self.__find_many(**filters))
        return result.all()

    async def find_all(self, pageable: Pageable = None) -> List[T]:
        result: Result[Any] = await self._session.execute(select(self._entity))
        return result.scalars().all()

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

    async def delete_by_id(self, id: _PKIdentityArgument) -> None:
        record = self.find_by_id(id=id)
        if record is not None:
            await self._session.delete(record)
            await self._session.flush()

    async def update_from(self, id: _PKIdentityArgument, dto, exclude: list) -> T:
        exclude_items: dict = dict(zip(exclude, exclude))
        entity: T = self.find_by_id(id=id)
        if entity is not None:
            for column in self._entity.__table__.columns:
                if column != self._entity.id:
                    set_value = getattr(dto, column.name, None)
                    if set_value is not None and exclude_items.get(column.name) is None:
                        setattr(entity, column.name, set_value)
            return await self.update(record=entity)
        else:
            raise Exception(f"Entity {id} not found")
