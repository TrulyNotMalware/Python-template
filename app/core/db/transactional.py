from collections.abc import Awaitable, Callable
from functools import wraps

from app.core.db import session


class Transactional:
    def __call__[**P, T](
        self,
        func: Callable[P, Awaitable[T]],
    ) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def _transactional(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                result = await func(*args, **kwargs)
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e

            return result

        return _transactional
