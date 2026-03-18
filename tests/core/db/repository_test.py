import pytest

from app.user.model.user import User, UserRepository


@pytest.fixture
def repository() -> UserRepository:
    return UserRepository()


@pytest.fixture
async def test_user(repository: UserRepository) -> User:
    user = User(password="<PASSWORD>", email="<EMAIL>", nickname="test_user")
    return await repository.save(entity=user)


@pytest.mark.asyncio
async def test_find_by_nickname(repository: UserRepository, test_user: User) -> None:
    users: list[User] = await repository.find_by(nickname="test_user")
    assert len(users) > 0
    user: User = users.pop()
    assert user.nickname == "test_user"


@pytest.mark.asyncio
async def test_save_user(repository: UserRepository) -> None:
    user = User(password="<PASSWORD>", email="<EMAIL_NEW>", nickname="new_user")
    saved: User = await repository.save(entity=user)
    assert saved.email == "<EMAIL_NEW>"
    assert saved.nickname == "new_user"
