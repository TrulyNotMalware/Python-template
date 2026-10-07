import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class ResponseLogMiddleware:
    """Log method, path, status and size of every HTTP response at DEBUG level.

    Headers and body content never reach the log: they can carry credentials.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status: int | None = None
        size = 0

        async def send_and_count(message: Message) -> None:
            nonlocal status, size
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body":
                size += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, send_and_count)
        finally:
            # Also when the application raised: no status means the error
            # escaped before a response started, and the outer 500 is not seen.
            logger.debug(
                "%s %s -> %s (%d bytes)",
                scope["method"],
                scope["path"],
                "unhandled" if status is None else status,
                size,
            )
