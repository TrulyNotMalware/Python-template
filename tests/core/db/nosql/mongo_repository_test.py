import pytest

from app.core.db.protocol import Pageable, SortOption
from tests.core.db.nosql.conftest import ArticleDocument, ArticleRepository


@pytest.mark.asyncio
async def test_save(repository: ArticleRepository) -> None:
    article = ArticleDocument(title="Test", content="Body", author="author1")
    saved = await repository.save(entity=article)

    assert saved.id is not None
    assert saved.title == "Test"
    assert saved.content == "Body"
    assert saved.author == "author1"


@pytest.mark.asyncio
async def test_find_by_pk(
    repository: ArticleRepository, saved_article: ArticleDocument
) -> None:
    found = await repository.find_by_pk(pk=saved_article.id)

    assert found is not None
    assert found.id == saved_article.id
    assert found.title == saved_article.title


@pytest.mark.asyncio
async def test_find_by_pk_not_found(repository: ArticleRepository) -> None:
    from bson import ObjectId

    fake_pk = str(ObjectId())
    found = await repository.find_by_pk(pk=fake_pk)

    assert found is None


@pytest.mark.asyncio
async def test_find_by(
    repository: ArticleRepository, saved_article: ArticleDocument
) -> None:
    results = await repository.find_by(author="tester")

    assert len(results) >= 1
    assert all(r.author == "tester" for r in results)


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_find_all(repository: ArticleRepository) -> None:
    await repository.save(
        entity=ArticleDocument(title="First", content="c", author="a")
    )
    await repository.save(
        entity=ArticleDocument(title="Second", content="c", author="b")
    )

    results = await repository.find_all()

    assert len(results) >= 2


@pytest.mark.asyncio
async def test_find_all_with_pageable(repository: ArticleRepository) -> None:
    for i in range(5):
        await repository.save(
            entity=ArticleDocument(title=f"Doc{i}", content="c", author="a")
        )

    pageable = Pageable(sort="title", size=2, page=1, sort_option=SortOption.ASC)
    results = await repository.find_all(pageable=pageable)

    assert len(results) == 2


@pytest.mark.asyncio
async def test_update(
    repository: ArticleRepository, saved_article: ArticleDocument
) -> None:
    saved_article.title = "Updated Title"
    updated = await repository.update(entity=saved_article)

    assert updated.title == "Updated Title"

    found = await repository.find_by_pk(pk=saved_article.id)
    assert found is not None
    assert found.title == "Updated Title"


@pytest.mark.asyncio
async def test_update_raises_without_id(repository: ArticleRepository) -> None:
    article = ArticleDocument(title="No ID", content="c", author="a")

    with pytest.raises(ValueError, match="Entity id is required"):
        await repository.update(entity=article)


@pytest.mark.asyncio
async def test_update_from(
    repository: ArticleRepository, saved_article: ArticleDocument
) -> None:
    class UpdateDto:
        title = "Patched Title"
        content = None
        author = None

    updated = await repository.update_from(
        pk=saved_article.id,
        dto=UpdateDto(),
        exclude=[],
    )

    assert updated.title == "Patched Title"
    assert updated.content == saved_article.content

    found = await repository.find_by_pk(pk=saved_article.id)
    assert found is not None
    assert found.title == "Patched Title"


@pytest.mark.asyncio
async def test_update_from_with_exclude(
    repository: ArticleRepository, saved_article: ArticleDocument
) -> None:
    class UpdateDto:
        title = "Should Be Ignored"
        content = "New Content"
        author = None

    original_title = saved_article.title
    await repository.update_from(
        pk=saved_article.id,
        dto=UpdateDto(),
        exclude=["title"],
    )

    found = await repository.find_by_pk(pk=saved_article.id)
    assert found is not None
    assert found.title == original_title
    assert found.content == "New Content"


@pytest.mark.asyncio
async def test_update_from_not_found(repository: ArticleRepository) -> None:
    from bson import ObjectId

    fake_pk = str(ObjectId())

    with pytest.raises(ValueError, match="not found"):
        await repository.update_from(pk=fake_pk, dto=object(), exclude=[])


@pytest.mark.asyncio
async def test_delete_by_id(
    repository: ArticleRepository, saved_article: ArticleDocument
) -> None:
    await repository.delete_by_id(pk=saved_article.id)

    found = await repository.find_by_pk(pk=saved_article.id)
    assert found is None


@pytest.mark.asyncio
async def test_delete_by_id_not_existing(repository: ArticleRepository) -> None:
    from bson import ObjectId

    fake_pk = str(ObjectId())

    await repository.delete_by_id(pk=fake_pk)
