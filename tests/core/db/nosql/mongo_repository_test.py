from collections.abc import Awaitable, Callable
from typing import Any, Self

import pytest
from bson import ObjectId
from pydantic import BaseModel, ValidationError, model_validator
from pymongo.asynchronous.database import AsyncDatabase

from app.core.db.nosql.document import MongoDocument
from app.core.db.nosql.repository import MongoRepository
from app.core.db.protocol import Pageable, SortOption
from tests.core.db.nosql.conftest import ArticleDocument, ArticleRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")

INVALID_ID = "not-an-object-id"


class TrackedDocument(MongoDocument):
    title: str
    slug: str = ""
    views: int = 0

    @model_validator(mode="after")
    def _derive_slug(self) -> Self:
        self.slug = self.title.lower()
        return self


def _id_of(article: MongoDocument) -> str:
    assert article.id is not None
    return article.id


@pytest.fixture
def tracked_repository(
    database: AsyncDatabase[dict[str, Any]],
) -> MongoRepository[TrackedDocument]:
    return MongoRepository(
        database=database, collection_name="tracked", document_class=TrackedDocument
    )


async def _stored(
    database: AsyncDatabase[dict[str, Any]], document: MongoDocument
) -> dict[str, Any]:
    # Read the raw document: find_by_pk re-runs the validators and would hide
    # a derived field that was returned but never written.
    raw = await database["tracked"].find_one({"_id": ObjectId(_id_of(document))})
    assert raw is not None
    return raw


async def test_save(repository: ArticleRepository) -> None:
    article = ArticleDocument(title="Test", content="Body", author="author1")
    saved = await repository.save(entity=article)

    assert saved.id is not None
    assert saved.title == "Test"
    assert saved.content == "Body"
    assert saved.author == "author1"


async def test_find_by_pk(
    repository: ArticleRepository, saved_article: ArticleDocument
) -> None:
    found = await repository.find_by_pk(pk=_id_of(saved_article))

    assert found is not None
    assert found.id == saved_article.id
    assert found.title == saved_article.title


async def test_find_by_pk_not_found(repository: ArticleRepository) -> None:
    fake_pk = str(ObjectId())
    found = await repository.find_by_pk(pk=fake_pk)

    assert found is None


async def test_find_by(
    repository: ArticleRepository, saved_article: ArticleDocument
) -> None:
    results = await repository.find_by(author="tester")

    assert [r.id for r in results] == [saved_article.id]


async def test_find_by_multiple_filters(repository: ArticleRepository) -> None:
    await repository.save(
        entity=ArticleDocument(title="A", content="x", author="alice")
    )
    await repository.save(
        entity=ArticleDocument(title="B", content="y", author="alice")
    )
    await repository.save(entity=ArticleDocument(title="A", content="z", author="bob"))

    results = await repository.find_by(title="A", author="alice")

    assert len(results) == 1
    assert results[0].title == "A"
    assert results[0].author == "alice"


async def test_find_all(repository: ArticleRepository) -> None:
    await repository.save(
        entity=ArticleDocument(title="First", content="c", author="a")
    )
    await repository.save(
        entity=ArticleDocument(title="Second", content="c", author="b")
    )

    results = await repository.find_all()

    assert sorted(r.title for r in results) == ["First", "Second"]


async def test_find_all_with_pageable(repository: ArticleRepository) -> None:
    for i in range(5):
        await repository.save(
            entity=ArticleDocument(title=f"Doc{i}", content="c", author="a")
        )

    pageable = Pageable(sort="title", size=2, page=1, sort_option=SortOption.ASC)
    results = await repository.find_all(pageable=pageable)

    assert [r.title for r in results] == ["Doc0", "Doc1"]

    pageable = Pageable(sort="title", size=2, page=2, sort_option=SortOption.DESC)
    results = await repository.find_all(pageable=pageable)

    assert [r.title for r in results] == ["Doc2", "Doc1"]


async def test_update(
    repository: ArticleRepository, saved_article: ArticleDocument
) -> None:
    saved_article.title = "Updated Title"
    updated = await repository.update(entity=saved_article)

    assert updated.title == "Updated Title"

    found = await repository.find_by_pk(pk=_id_of(saved_article))
    assert found is not None
    assert found.title == "Updated Title"


async def test_update_raises_without_id(repository: ArticleRepository) -> None:
    article = ArticleDocument(title="No ID", content="c", author="a")

    with pytest.raises(ValueError, match="Entity id is required"):
        await repository.update(entity=article)


async def test_update_from(
    repository: ArticleRepository, saved_article: ArticleDocument
) -> None:
    class UpdateDto:
        title = "Patched Title"
        content = None
        author = None

    updated = await repository.update_from(
        pk=_id_of(saved_article),
        dto=UpdateDto(),
        exclude=[],
    )

    assert updated.title == "Patched Title"
    assert updated.content == saved_article.content

    found = await repository.find_by_pk(pk=_id_of(saved_article))
    assert found is not None
    assert found.title == "Patched Title"


async def test_update_from_with_exclude(
    repository: ArticleRepository, saved_article: ArticleDocument
) -> None:
    class UpdateDto:
        title = "Should Be Ignored"
        content = "New Content"
        author = None

    original_title = saved_article.title
    await repository.update_from(
        pk=_id_of(saved_article),
        dto=UpdateDto(),
        exclude=["title"],
    )

    found = await repository.find_by_pk(pk=_id_of(saved_article))
    assert found is not None
    assert found.title == original_title
    assert found.content == "New Content"


async def test_update_from_pydantic_dto_applies_only_set_fields(
    repository: ArticleRepository, saved_article: ArticleDocument
) -> None:
    class ArticlePatch(BaseModel):
        title: str | None = None
        content: str | None = None
        author: str = "patch-default"

    await repository.update_from(
        pk=_id_of(saved_article),
        dto=ArticlePatch(title="Should Be Ignored", content="New Content"),
        exclude=["title"],
    )

    found = await repository.find_by_pk(pk=_id_of(saved_article))
    assert found is not None
    assert found.title == saved_article.title
    assert found.content == "New Content"
    # author was never set on the patch, so its default must not be written.
    assert found.author == saved_article.author


async def test_update_from_rejects_null_for_required_field(
    repository: ArticleRepository, saved_article: ArticleDocument
) -> None:
    class ArticlePatch(BaseModel):
        title: str | None = None

    with pytest.raises(ValidationError):
        await repository.update_from(
            pk=_id_of(saved_article), dto=ArticlePatch(title=None), exclude=[]
        )

    found = await repository.find_by_pk(pk=_id_of(saved_article))
    assert found is not None
    assert found.title == saved_article.title


async def test_update_from_stores_validator_derived_fields(
    database: AsyncDatabase[dict[str, Any]],
    tracked_repository: MongoRepository[TrackedDocument],
) -> None:
    class TitlePatch(BaseModel):
        title: str | None = None

    saved = await tracked_repository.save(entity=TrackedDocument(title="Hello"))

    updated = await tracked_repository.update_from(
        pk=_id_of(saved), dto=TitlePatch(title="World"), exclude=[]
    )

    assert updated.slug == "world"
    stored = await _stored(database, saved)
    assert stored["title"] == "World"
    assert stored["slug"] == "world"


async def test_update_from_plain_object_is_coerced_and_validated(
    database: AsyncDatabase[dict[str, Any]],
    tracked_repository: MongoRepository[TrackedDocument],
) -> None:
    class ViewsAsText:
        views = "5"

    class ViewsNotANumber:
        views = "abc"

    saved = await tracked_repository.save(entity=TrackedDocument(title="Hello"))

    updated = await tracked_repository.update_from(
        pk=_id_of(saved), dto=ViewsAsText(), exclude=[]
    )

    assert updated.views == 5
    # The string "5" would not compare equal to 5, so this pins the stored type.
    assert (await _stored(database, saved))["views"] == 5

    with pytest.raises(ValidationError):
        await tracked_repository.update_from(
            pk=_id_of(saved), dto=ViewsNotANumber(), exclude=[]
        )

    assert (await _stored(database, saved))["views"] == 5


async def test_update_from_not_found(repository: ArticleRepository) -> None:
    fake_pk = str(ObjectId())

    with pytest.raises(ValueError, match="not found"):
        await repository.update_from(pk=fake_pk, dto=object(), exclude=[])


async def test_delete_by_id(
    repository: ArticleRepository, saved_article: ArticleDocument
) -> None:
    await repository.delete_by_id(pk=_id_of(saved_article))

    found = await repository.find_by_pk(pk=_id_of(saved_article))
    assert found is None


async def test_delete_by_id_not_existing(repository: ArticleRepository) -> None:
    fake_pk = str(ObjectId())

    await repository.delete_by_id(pk=fake_pk)


@pytest.mark.parametrize(
    "call",
    [
        lambda repo: repo.find_by_pk(pk=INVALID_ID),
        lambda repo: repo.find_by(id=INVALID_ID),
        lambda repo: repo.update(
            entity=ArticleDocument(id=INVALID_ID, title="t", content="c", author="a")
        ),
        lambda repo: repo.update_from(pk=INVALID_ID, dto=object(), exclude=[]),
        lambda repo: repo.delete_by_id(pk=INVALID_ID),
    ],
    ids=["find_by_pk", "find_by", "update", "update_from", "delete_by_id"],
)
async def test_invalid_id_raises_value_error(
    repository: ArticleRepository,
    call: Callable[[ArticleRepository], Awaitable[object]],
) -> None:
    with pytest.raises(ValueError, match="invalid id"):
        await call(repository)


@pytest.mark.parametrize(
    "filters",
    [{"$where": "true"}, {"author": {"$ne": None}}],
    ids=["operator_key", "operator_value"],
)
async def test_find_by_rejects_operator_filters(
    repository: ArticleRepository,
    saved_article: ArticleDocument,
    filters: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="unsupported filter"):
        await repository.find_by(**filters)
