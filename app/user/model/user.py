from sqlalchemy import Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, SQLRepository
from app.core.db.session import session


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    password: Mapped[str] = mapped_column(Unicode(255))
    email: Mapped[str] = mapped_column(Unicode(255), unique=True)
    nickname: Mapped[str] = mapped_column(Unicode(255), unique=True)
    is_admin: Mapped[bool] = mapped_column(default=False)


class UserRepository(SQLRepository[User]):
    def __init__(self) -> None:
        super().__init__(session=session, entity=User)
