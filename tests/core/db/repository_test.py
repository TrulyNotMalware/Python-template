from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, SQLRepository
from app.core.db.protocol import Pageable, SortOption
from app.core.db.session import WRITING_ENGINE_NAME, session
from app.user.model.user import User, UserRepository
from app.user.schemas.user import GetUserListResponseSchema


class UserUpdate(BaseModel):
    email: str | None = None
    nickname: str | None = None


class IsolatedBase(Base):
    """Keeps test tables off Base.metadata, which every app lifespan creates."""

    __abstract__ = True
    metadata = MetaData()


class Tag(IsolatedBase):
    """Primary key attribute named unlike its column, and a nullable column."""

    __tablename__ = "test_tags"

    tag_id: Mapped[int] = mapped_column("id", primary_key=True)
    name: Mapped[str]
    note: Mapped[str | None]


class TagRepository(SQLRepository[Tag]):
    def __init__(self) -> None:
        super().__init__(session=session, entity=Tag)


class TagUpdate(BaseModel):
    tag_id: int | None = None
    name: str | None = None
    note: str | None = None


@pytest.fixture
def repository(session_id: str) -> UserRepository:
    return UserRepository()


@pytest.fixture(scope="module")
async def tag_table(db_engines: dict[str, AsyncEngine]) -> AsyncIterator[None]:
    engine = db_engines[WRITING_ENGINE_NAME]
    async with engine.begin() as connection:
        await connection.run_sync(IsolatedBase.metadata.create_all)
    yield
    async with engine.begin() as connection:
        await connection.run_sync(IsolatedBase.metadata.drop_all)


@pytest.fixture
async def tag(tag_table: None, session_id: str) -> Tag:
    return await TagRepository().save(Tag(name="first", note="kept"))


@pytest.fixture
async def test_user(repository: UserRepository) -> User:
    user = User(password="<PASSWORD>", email="<EMAIL>", nickname="test_user")
    return await repository.save(entity=user)


async def test_find_by_nickname(repository: UserRepository, test_user: User) -> None:
    users: list[User] = await repository.find_by(nickname="test_user")
    assert len(users) > 0
    user: User = users.pop()
    assert user.nickname == "test_user"


async def test_save_user(repository: UserRepository) -> None:
    user = User(password="<PASSWORD>", email="<EMAIL_NEW>", nickname="new_user")
    saved: User = await repository.save(entity=user)
    assert saved.email == "<EMAIL_NEW>"
    assert saved.nickname == "new_user"
    assert saved.is_admin is False


async def test_find_by_pk(repository: UserRepository, test_user: User) -> None:
    found = await repository.find_by_pk(pk=test_user.id)
    assert found is not None
    assert found.nickname == "test_user"


async def test_find_all_pages_in_sort_order(repository: UserRepository) -> None:
    for name in ("a", "b", "c"):
        await repository.save(User(password="pw", email=f"{name}@x", nickname=name))

    page = await repository.find_all(
        Pageable(sort="nickname", size=2, page=1, sort_option=SortOption.DESC)
    )
    assert [user.nickname for user in page] == ["c", "b"]


@pytest.mark.parametrize(
    ("name", "value"), [("metadata", "x"), ("__tablename__", "users"), ("missing", 1)]
)
async def test_find_by_rejects_non_column_filter(
    repository: UserRepository, test_user: User, name: str, value: object
) -> None:
    with pytest.raises(ValueError, match=f"Invalid Column name {name}"):
        await repository.find_by(**{name: value})


@pytest.mark.parametrize("sort", ["metadata", "__tablename__", "missing"])
async def test_find_all_rejects_non_column_sort(
    repository: UserRepository, sort: str
) -> None:
    with pytest.raises(ValueError, match=f"Invalid sort column: {sort}"):
        await repository.find_all(Pageable(sort=sort, size=1, page=1))


@pytest.mark.parametrize(
    ("size", "page", "message"),
    [(0, 1, "size must be greater than 0"), (1, 0, "page must be greater than 0")],
)
def test_pageable_rejects_non_positive_values(
    size: int, page: int, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Pageable(sort="id", size=size, page=page)


def test_pageable_rejects_plain_string_sort_option() -> None:
    with pytest.raises(TypeError, match="SortOption"):
        Pageable(sort="id", size=1, page=1, sort_option="ASC")  # type: ignore[arg-type]


async def test_update_from_model_applies_only_set_fields(
    repository: UserRepository, test_user: User
) -> None:
    updated = await repository.update_from(
        pk=test_user.id, dto=UserUpdate(nickname="renamed"), exclude=[]
    )

    assert updated.nickname == "renamed"
    assert updated.email == "<EMAIL>"


async def test_update_from_respects_exclude(
    repository: UserRepository, test_user: User
) -> None:
    updated = await repository.update_from(
        pk=test_user.id,
        dto=UserUpdate(email="new@x", nickname="renamed"),
        exclude=["email"],
    )

    assert updated.nickname == "renamed"
    assert updated.email == "<EMAIL>"


async def test_update_from_model_writes_explicit_none(tag: Tag) -> None:
    updated = await TagRepository().update_from(
        pk=tag.tag_id, dto=TagUpdate(note=None), exclude=[]
    )

    assert updated.note is None
    assert updated.name == "first"


@pytest.mark.parametrize(
    "dto",
    [
        TagUpdate(tag_id=999, name="renamed"),
        SimpleNamespace(tag_id=999, name="renamed", note=None),
    ],
    ids=["model", "plain-object"],
)
async def test_update_from_keeps_primary_key_named_unlike_its_column(
    tag: Tag, dto: object
) -> None:
    original_id = tag.tag_id

    updated = await TagRepository().update_from(pk=original_id, dto=dto, exclude=[])

    assert updated.tag_id == original_id
    assert updated.name == "renamed"
    assert updated.note == "kept"


async def test_update_from_missing_entity_raises(repository: UserRepository) -> None:
    with pytest.raises(ValueError, match="not found"):
        await repository.update_from(pk=-1, dto=UserUpdate(), exclude=[])


async def test_delete_by_id(repository: UserRepository, test_user: User) -> None:
    await repository.delete_by_id(pk=test_user.id)

    assert await repository.find_by_pk(pk=test_user.id) is None


def test_response_schema_reads_orm_attributes() -> None:
    user = User(id=1, password="<PASSWORD>", email="<EMAIL>", nickname="test_user")

    schema = GetUserListResponseSchema.model_validate(user)

    assert schema == GetUserListResponseSchema(
        id=1, email="<EMAIL>", nickname="test_user"
    )
