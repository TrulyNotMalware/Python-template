from collections.abc import Callable, Coroutine
from typing import Any
from uuid import uuid4

from .session import reset_session_context, session, set_session_context


def standalone_session[**P](
    func: Callable[P, Coroutine[Any, Any, None]],
) -> Callable[P, Coroutine[Any, Any, None]]:
    async def _standalone_session(*args: P.args, **kwargs: P.kwargs) -> None:
        session_id = str(uuid4())
        context = set_session_context(session_id=session_id)

        try:
            await func(*args, **kwargs)
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.remove()
            reset_session_context(context=context)

    return _standalone_session
