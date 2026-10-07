import pytest

from app.core.db.nosql.client import create_mongo_client

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_create_mongo_client_sets_timeouts() -> None:
    # The client connects lazily, so this unreachable address is never contacted.
    client = create_mongo_client("mongodb://127.0.0.1:1")
    try:
        assert client.options.timeout == 10.0
        assert client.options.server_selection_timeout == 5.0
        assert client.options.pool_options.connect_timeout == 5.0
    finally:
        await client.close()
