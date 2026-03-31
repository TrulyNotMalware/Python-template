import pytest
from mongomock_motor import AsyncMongoMockClient

from app.core.db.nosql.document import MongoDocument
from app.core.db.nosql.repository import MongoRepository


class ArticleDocument(MongoDocument):
    title: str
    content: str
    author: str


class ArticleRepository(MongoRepository[ArticleDocument]):
    def __init__(self, database):
        super().__init__(
            database=database,
            collection_name="articles",
            document_class=ArticleDocument,
        )


@pytest.fixture
def database():
    client = AsyncMongoMockClient()
    return client["testdb"]


@pytest.fixture
def repository(database) -> ArticleRepository:
    return ArticleRepository(database=database)


@pytest.fixture
async def saved_article(repository: ArticleRepository) -> ArticleDocument:
    article = ArticleDocument(title="Hello", content="World", author="tester")
    return await repository.save(entity=article)
