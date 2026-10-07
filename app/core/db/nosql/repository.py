from collections.abc import Mapping
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pydantic import BaseModel
from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

from app.core.db.nosql.document import MongoDocument
from app.core.db.protocol import Pageable, SortOption


def _object_id(pk: str) -> ObjectId:
    try:
        return ObjectId(pk)
    except (InvalidId, TypeError) as exc:
        raise ValueError(f"invalid id: {pk!r}") from exc


class MongoRepository[T: MongoDocument]:
    def __init__(
        self,
        database: AsyncDatabase[dict[str, Any]],
        collection_name: str,
        document_class: type[T],
    ) -> None:
        self._collection: AsyncCollection[dict[str, Any]] = database[collection_name]
        self._document_class = document_class

    @staticmethod
    def _to_doc(entity: MongoDocument) -> dict[str, Any]:
        # Fields are stored as dumped in Python mode. Values BSON cannot encode by
        # default (Decimal needs Decimal128, uuid.UUID needs a uuidRepresentation on
        # the client) are out of scope here and fail in the driver.
        data = entity.model_dump(mode="python", exclude={"id"})
        if entity.id is not None:
            data["_id"] = _object_id(entity.id)
        return data

    def _from_doc(self, doc: dict[str, Any]) -> T:
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        return self._document_class(**doc)

    @staticmethod
    def _build_filter(filters: dict[str, Any]) -> dict[str, Any]:
        mongo_filter: dict[str, Any] = {}
        for key, value in filters.items():
            # Equality filters only: an operator key or a document value would let
            # a caller inject query operators such as {"$ne": None}.
            if key.startswith("$") or isinstance(value, Mapping):
                raise ValueError(f"unsupported filter for field {key!r}")
            if key == "id":
                mongo_filter["_id"] = _object_id(value)
            else:
                mongo_filter[key] = value
        return mongo_filter

    async def find_by_pk(self, pk: str) -> T | None:
        doc = await self._collection.find_one({"_id": _object_id(pk)})
        if doc is None:
            return None
        return self._from_doc(doc)

    async def find_by(self, **filters: Any) -> list[T]:
        cursor = self._collection.find(self._build_filter(filters))
        return [self._from_doc(doc) for doc in await cursor.to_list(None)]

    async def find_all(self, pageable: Pageable | None = None) -> list[T]:
        cursor = self._collection.find()
        if pageable is not None:
            direction = (
                DESCENDING if pageable.sort_option == SortOption.DESC else ASCENDING
            )
            offset = (pageable.page - 1) * pageable.size
            cursor = (
                cursor.sort(pageable.sort, direction).skip(offset).limit(pageable.size)
            )
        return [self._from_doc(doc) for doc in await cursor.to_list(None)]

    async def save(self, entity: T) -> T:
        data = self._to_doc(entity)
        result = await self._collection.insert_one(data)
        entity.id = str(result.inserted_id)
        return entity

    async def update(self, entity: T) -> T:
        if entity.id is None:
            raise ValueError("Entity id is required for update.")
        data = self._to_doc(entity)
        object_id = data.pop("_id")
        await self._collection.replace_one({"_id": object_id}, data)
        return entity

    async def update_from(self, pk: str, dto: object, exclude: list[str]) -> T:
        """Copy field values from ``dto`` onto the document with id ``pk``.

        A Pydantic model contributes only the fields that were set, so an explicit
        ``None`` clears a field and an omitted field is left alone. Any other
        object contributes every matching attribute that is not ``None``.
        The id and the names in ``exclude`` are never taken from ``dto``. The merged
        document is validated before anything is written, so a value the document
        model rejects (``None`` for a required field) raises ``ValidationError``
        and leaves the stored document unchanged. Every field whose validated value
        changed is written, including fields a model validator derives from the
        copied ones, so the stored document matches the returned one.
        """
        object_id = _object_id(pk)
        entity: T | None = await self.find_by_pk(pk)
        if entity is None:
            raise ValueError(f"Entity {pk} not found.")

        exclude_set: set[str] = set(exclude) | {"id"}
        keys = [
            key for key in self._document_class.model_fields if key not in exclude_set
        ]
        picked: dict[str, Any] = {}

        if isinstance(dto, BaseModel):
            changes = dto.model_dump(exclude_unset=True, exclude=exclude_set)
            picked = {key: changes[key] for key in keys if key in changes}
        else:
            for key in keys:
                value = getattr(dto, key, None)
                if value is not None:
                    picked[key] = value

        before = entity.model_dump(mode="python")
        merged = self._document_class.model_validate(before | picked)
        update_data = {
            key: value
            for key, value in merged.model_dump(mode="python").items()
            if key != "id" and (key in picked or value != before.get(key))
        }
        if update_data:
            await self._collection.update_one(
                {"_id": object_id},
                {"$set": update_data},
            )
        return merged

    async def delete_by_id(self, pk: str) -> None:
        await self._collection.delete_one({"_id": _object_id(pk)})
