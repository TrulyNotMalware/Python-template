from typing import Any

from pymongo import AsyncMongoClient


def create_mongo_client(url: str) -> AsyncMongoClient[dict[str, Any]]:
    """Create an async MongoDB client with explicit timeouts.

    ``timeoutMS`` bounds every operation end to end (draining a cursor included), so
    a server that stops answering after the connection is made cannot block a
    request forever. The client connects lazily and is bound to the event loop that
    first uses it, so create it inside the application lifespan (or a session-loop
    test fixture) and release it there with ``await client.close()``.
    """
    return AsyncMongoClient(
        url,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        timeoutMS=10_000,
    )
