from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps
from typing import Any

from app.core.db.session import session

_DEPTH_KEY = "transactional_depth"


class Transactional:
    """Commit the current session when the outermost decorated call returns.

    Nested decorated calls join the outer call: only the outermost one commits,
    or rolls back when the call raises. The session's transaction state is not
    consulted, because autobegin starts a transaction on the first read too.

    Limitation: a nested call does not mark the transaction rollback-only. If the
    outer call catches an exception from a nested call and returns normally, the
    outer call commits whatever the session still holds.
    """

    def __call__[**P, T](
        self,
        func: Callable[P, Awaitable[T]],
    ) -> Callable[P, Coroutine[Any, Any, T]]:
        @wraps(func)
        async def _transactional(*args: P.args, **kwargs: P.kwargs) -> T:
            current = session()
            depth: int = current.info.get(_DEPTH_KEY, 0)
            current.info[_DEPTH_KEY] = depth + 1
            try:
                result = await func(*args, **kwargs)
                if depth == 0:
                    await current.commit()
            except BaseException:
                if depth == 0:
                    await current.rollback()
                raise
            finally:
                current.info[_DEPTH_KEY] = depth
            return result

        return _transactional
