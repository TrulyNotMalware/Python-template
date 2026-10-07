from uuid import uuid4

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.db.session import reset_session_context, session, set_session_context


class SQLAlchemyMiddleware:
    """Give each HTTP request and WebSocket connection its own session scope."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            # The lifespan scope runs for the whole process; it gets no session.
            await self.app(scope, receive, send)
            return

        session_id = str(uuid4())
        context = set_session_context(session_id=session_id)

        try:
            await self.app(scope, receive, send)
        finally:
            await session.remove()
            reset_session_context(context=context)
