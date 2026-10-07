import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.db.nosql.client import create_mongo_client
from app.core.db.nosql.document import MongoDocument
from app.core.db.nosql.repository import MongoRepository


class ArticleDocument(MongoDocument):
    title: str
    content: str
    author: str


class ArticleRepository(MongoRepository[ArticleDocument]):
    def __init__(self, database: AsyncDatabase[dict[str, Any]]) -> None:
        super().__init__(
            database=database,
            collection_name="articles",
            document_class=ArticleDocument,
        )


# A module-level pytest.skip in this conftest would crash pytest when this
# directory is the command-line target, so the skip happens in a fixture.
@pytest.fixture(scope="session")
def mongo_test_url() -> str:
    url = os.environ.get("MONGO_TEST_URL", "")
    if not url:
        pytest.skip(
            "MONGO_TEST_URL is not set; run `source scripts/test-env.sh` to point "
            "the MongoDB tests at the local infra"
        )
    return url


# AsyncMongoClient is bound to the event loop that first uses it, so the client and
# every async fixture and test using it share the session loop.
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def mongo_client(
    mongo_test_url: str,
) -> AsyncIterator[AsyncMongoClient[dict[str, Any]]]:
    client = create_mongo_client(mongo_test_url)
    try:
        await client.admin.command("ping")
        yield client
    finally:
        await client.close()


@pytest_asyncio.fixture(loop_scope="session")
async def database(
    mongo_client: AsyncMongoClient[dict[str, Any]],
) -> AsyncIterator[AsyncDatabase[dict[str, Any]]]:
    name = f"python_template_test_{uuid4().hex[:8]}"
    try:
        yield mongo_client[name]
    finally:
        await mongo_client.drop_database(name)


@pytest.fixture
def repository(database: AsyncDatabase[dict[str, Any]]) -> ArticleRepository:
    return ArticleRepository(database=database)


@pytest_asyncio.fixture(loop_scope="session")
async def saved_article(repository: ArticleRepository) -> ArticleDocument:
    article = ArticleDocument(title="Hello", content="World", author="tester")
    return await repository.save(entity=article)
