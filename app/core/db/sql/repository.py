import abc
from typing import Any, override

from pydantic import BaseModel
from sqlalchemy import ColumnElement, Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_scoped_session
from sqlalchemy.inspection import inspect

from app.core.db.protocol import GenericRepository, Pageable, PrimaryKey, SortOption
from app.core.db.session import Base


class SQLRepository[T: Base](GenericRepository[T], abc.ABC):
    """Repository over the context-scoped session. It flushes and never commits."""

    def __init__(
        self, session: async_scoped_session[AsyncSession], entity: type[T]
    ) -> None:
        self._session = session
        self._entity = entity

    def __find_by_pk(self, pk: PrimaryKey) -> Select[T]:
        inspector = inspect(self._entity)
        return select(self._entity).where(inspector.primary_key[0] == pk)

    @override
    async def find_by_pk(self, pk: PrimaryKey) -> T | None:
        result = await self._session.execute(self.__find_by_pk(pk=pk))
        return result.scalars().first()

    def __find_many(self, **filters: Any) -> Select[T]:
        base = select(self._entity)
        columns = inspect(self._entity).column_attrs
        where_case: list[ColumnElement[bool]] = []
        for key, value in filters.items():
            if key not in columns:
                raise ValueError(f"Invalid Column name {key}.")
            where_case.append(columns[key].class_attribute == value)
        if not where_case:
            return base
        if len(where_case) == 1:
            return base.where(where_case[0])
        return base.where(and_(*where_case))

    @override
    async def find_by(self, **filters: Any) -> list[T]:
        result = await self._session.execute(self.__find_many(**filters))
        return list(result.scalars().all())

    @override
    async def find_all(self, pageable: Pageable | None = None) -> list[T]:
        query = select(self._entity)
        if pageable is not None:
            columns = inspect(self._entity).column_attrs
            if pageable.sort not in columns:
                raise ValueError(f"Invalid sort column: {pageable.sort}")
            column = columns[pageable.sort].class_attribute

            if pageable.sort_option is SortOption.DESC:
                order = column.desc()
            else:
                order = column.asc()
            query = query.order_by(order)

            offset = (pageable.page - 1) * pageable.size
            query = query.offset(offset).limit(pageable.size)

        result = await self._session.execute(query)
        return list(result.scalars().all())

    @override
    async def save(self, entity: T) -> T:
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    @override
    async def update(self, entity: T) -> T:
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    @override
    async def delete_by_id(self, pk: PrimaryKey) -> None:
        record = await self.find_by_pk(pk=pk)
        if record is not None:
            await self._session.delete(record)
            await self._session.flush()

    @override
    async def update_from(self, pk: PrimaryKey, dto: object, exclude: list[str]) -> T:
        """Copy column values from ``dto`` onto the entity with primary key ``pk``.

        A Pydantic model contributes only the fields that were set, so an explicit
        ``None`` clears a column and an omitted field is left alone. Any other
        object contributes every matching attribute that is not ``None``.
        Primary key columns and the names in ``exclude`` are never changed.
        """
        exclude_set: set[str] = set(exclude)
        entity: T | None = await self.find_by_pk(pk=pk)
        if entity is None:
            raise ValueError(f"Entity {pk} not found")

        mapper = inspect(self._entity)
        pk_keys = {mapper.get_property_by_column(col).key for col in mapper.primary_key}
        keys = [
            attr.key
            for attr in mapper.column_attrs
            if attr.key not in pk_keys and attr.key not in exclude_set
        ]

        if isinstance(dto, BaseModel):
            changes = dto.model_dump(exclude_unset=True, exclude=exclude_set)
            for key in keys:
                if key in changes:
                    setattr(entity, key, changes[key])
        else:
            for key in keys:
                value = getattr(dto, key, None)
                if value is not None:
                    setattr(entity, key, value)

        return await self.update(entity=entity)
