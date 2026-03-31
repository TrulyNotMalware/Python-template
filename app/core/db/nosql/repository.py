from __future__ import annotations

from typing import Any, TypeVar

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from app.core.db.nosql.document import MongoDocument
from app.core.db.protocol import Pageable

T = TypeVar("T", bound=MongoDocument)


class MongoRepository[T: MongoDocument]:
    def __init__(
        self,
        database: AsyncIOMotorDatabase,
        collection_name: str,
        document_class: type[T],
    ) -> None:
        self._collection = database[collection_name]
        self._document_class = document_class

    @staticmethod
    def _to_doc(entity: MongoDocument) -> dict[str, Any]:
        data = entity.model_dump(exclude={"id"})
        if entity.id is not None:
            data["_id"] = ObjectId(entity.id)
        return data

    def _from_doc(self, doc: dict[str, Any]) -> T:
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        return self._document_class(**doc)

    @staticmethod
    def _build_filter(filters: dict[str, Any]) -> dict[str, Any]:
        mongo_filter: dict[str, Any] = {}
        for key, value in filters.items():
            if key == "id":
                mongo_filter["_id"] = ObjectId(value)
            else:
                mongo_filter[key] = value
        return mongo_filter

    async def find_by_pk(self, pk: str) -> T | None:
        doc = await self._collection.find_one({"_id": ObjectId(pk)})
        if doc is None:
            return None
        return self._from_doc(doc)

    async def find_by(self, **filters: Any) -> list[T]:
        cursor = self._collection.find(self._build_filter(filters))
        return [self._from_doc(doc) async for doc in cursor]

    async def find_all(self, pageable: Pageable | None = None) -> list[T]:
        cursor = self._collection.find()
        if pageable is not None:
            sort_dir = DESCENDING if pageable.sort_option == "DESC" else ASCENDING
            offset = (pageable.page - 1) * pageable.size
            cursor = (
                cursor.sort(pageable.sort, sort_dir).skip(offset).limit(pageable.size)
            )
        return [self._from_doc(doc) async for doc in cursor]

    async def save(self, entity: T) -> T:
        data = self._to_doc(entity)
        result = await self._collection.insert_one(data)
        entity.id = str(result.inserted_id)
        return entity

    async def update(self, entity: T) -> T:
        if entity.id is None:
            raise ValueError("Entity id is required for update.")
        data = self._to_doc(entity)
        data.pop("_id", None)
        await self._collection.replace_one({"_id": ObjectId(entity.id)}, data)
        return entity

    async def update_from(self, pk: str, dto: Any, exclude: list[str]) -> T:
        entity: T | None = await self.find_by_pk(pk)
        if entity is None:
            raise ValueError(f"Entity {pk} not found.")

        exclude_set: set[str] = set(exclude) | {"id"}
        update_data: dict[str, Any] = {}

        for field in entity.model_dump(exclude=exclude_set):
            value = getattr(dto, field, None)
            if value is not None:
                setattr(entity, field, value)
                update_data[field] = value

        if update_data:
            await self._collection.update_one(
                {"_id": ObjectId(pk)},
                {"$set": update_data},
            )
        return entity

    async def delete_by_id(self, pk: str) -> None:
        await self._collection.delete_one({"_id": ObjectId(pk)})
