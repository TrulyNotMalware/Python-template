import unittest
from typing import List

from app.core.config.config import LocalConfig
from app.core.db import session
from app.core.db.session import init_tables
from app.user.model.user import UserRepository, User


class RepositoryTest(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.config = LocalConfig()# Test in local
        self.session = session
        self.repository = UserRepository()
        await init_tables()

        self.test_user = User(password="<PASSWORD>", email="<EMAIL>", nickname="test_user")
        self.test_user2 = User(password="<PASSWORD2>", email="<EMAIL2>", nickname="test_user2")
        self.test_user2 = User(password="<PASSWORD3>", email="<EMAIL3", nickname="test_user3")

        await self.repository.save(entity=self.test_user)
        await self.repository.save(entity=self.test_user2)

    async def test_repository_works_successfully(self):
        await self.repository.save(entity=self.test_user)
        users: List[User] = await self.repository.find_by(nickname="test_user")
        user: User = users.pop()