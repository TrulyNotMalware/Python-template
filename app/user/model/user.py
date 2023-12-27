from sqlalchemy import Column, Unicode, BigInteger, Boolean

from app.core.db import Base, session
from app.core.utils.common import SQLRepository


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    password = Column(Unicode(255), nullable=False)
    email = Column(Unicode(255), nullable=False, unique=True)
    nickname = Column(Unicode(255), nullable=False, unique=True)
    is_admin = Column(Boolean, default=False)


class UserRepository(SQLRepository[User]):
    def __init__(self):
        super().__init__(session=session, entity=User)
