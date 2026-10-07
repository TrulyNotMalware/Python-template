import pytest

from app.core.cache.idempotency_cache import AsyncIdempotencyCache
from app.core.cache.sync_idempotency_cache import SyncIdempotencyCache

TTL = 1.0
CLEANUP_INTERVAL = 60.0


@pytest.fixture
def async_cache() -> AsyncIdempotencyCache:
    """A fresh cache per test; calling the class returns the shared singleton."""
    instance = AsyncIdempotencyCache.__new__(AsyncIdempotencyCache)
    AsyncIdempotencyCache.__init__(instance, ttl=TTL, cleanup_interval=CLEANUP_INTERVAL)
    return instance


@pytest.fixture
def sync_cache() -> SyncIdempotencyCache:
    """A fresh cache per test; calling the class returns the shared singleton."""
    instance = SyncIdempotencyCache.__new__(SyncIdempotencyCache)
    SyncIdempotencyCache.__init__(instance, ttl=TTL, cleanup_interval=CLEANUP_INTERVAL)
    return instance
