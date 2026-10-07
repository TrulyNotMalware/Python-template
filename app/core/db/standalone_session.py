from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any
from uuid import uuid4

from app.core.db.session import reset_session_context, session, set_session_context


def standalone_session[**P, T](
    func: Callable[P, Coroutine[Any, Any, T]],
) -> Callable[P, Coroutine[Any, Any, T]]:
    """Run ``func`` in its own session scope, outside any request."""

    @wraps(func)
    async def _standalone_session(*args: P.args, **kwargs: P.kwargs) -> T:
        context = set_session_context(session_id=str(uuid4()))
        try:
            return await func(*args, **kwargs)
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.remove()
            reset_session_context(context=context)

    return _standalone_session
