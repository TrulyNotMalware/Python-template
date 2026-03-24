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
            if (
                session.in_transaction()
            ):  # FIXME: session.in_transaction not in type stub
                return await func(*args, **kwargs)

            async with session.begin():
                return await func(*args, **kwargs)

        return _transactional
