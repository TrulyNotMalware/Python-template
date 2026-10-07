import annotationlib
import asyncio
import functools
import hashlib
import hmac
import inspect
import json
import secrets
import time
from collections.abc import Awaitable, Callable, Coroutine, Iterator, Mapping
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, Secret, SecretBytes, SecretStr
from pydantic_core import to_jsonable_python
from starlette.status import HTTP_409_CONFLICT

from app.core.cache.protocol import CacheStatus
from app.core.utils import Singleton


class AsyncIdempotencyCache(metaclass=Singleton):
    """In-process TTL cache that runs a coroutine function at most once per key."""

    def __init__(self, ttl: float = 10.0, cleanup_interval: float = 30.0) -> None:
        self._cache: dict[str, tuple[Any, float]] = {}
        self.lock = asyncio.Lock()
        self._ttl = ttl
        self._cleanup_interval = cleanup_interval

    async def process(self, key: str, func: Callable[[], Awaitable[Any]]) -> Any:
        """Return the cached result for key, or run func once and cache its result.

        The lookup and the PROCESSING marker are written under one lock acquisition,
        so a concurrent duplicate gets HTTP 409 instead of running func again. A
        result of None is cached like any other value. If func raises or the caller
        is cancelled, the marker is removed so a retry can run.
        """
        async with self.lock:
            hit, cached = self._lookup(key)
            if hit:
                if cached is CacheStatus.PROCESSING:
                    raise HTTPException(
                        status_code=HTTP_409_CONFLICT,
                        detail=f"Already Processing idempotency key: {key}",
                    )
                return cached
            self._store(key, CacheStatus.PROCESSING)

        try:
            result = await func()
        except BaseException:
            await self.delete(key)
            raise
        await self.set(key, result)
        return result

    async def get(self, key: str) -> Any | None:
        """Return the cached value, or None when key is missing or expired.

        A cached None result looks like a miss here; process() tells them apart.
        """
        async with self.lock:
            _, value = self._lookup(key)
        return value

    async def set(self, key: str, result: Any) -> None:
        async with self.lock:
            self._store(key, result)

    async def delete(self, key: str) -> None:
        async with self.lock:
            self._cache.pop(key, None)

    async def evict_expired(self) -> None:
        async with self.lock:
            now = time.monotonic()
            expired = [k for k, (_, exp) in self._cache.items() if now > exp]
            for k in expired:
                del self._cache[k]

    async def evict_loop(self) -> None:
        """Call evict_expired() every cleanup_interval seconds until cancelled."""
        while True:
            await asyncio.sleep(self._cleanup_interval)
            await self.evict_expired()

    def _lookup(self, key: str) -> tuple[bool, Any]:
        """Return (hit, value) for key and drop it when expired; hold the lock."""
        entry = self._cache.get(key)
        if entry is None:
            return False, None
        value, expire_at = entry
        if time.monotonic() > expire_at:
            del self._cache[key]
            return False, None
        return True, value

    def _store(self, key: str, value: Any) -> None:
        """Store value for key with a fresh TTL; hold the lock."""
        self._cache[key] = (value, time.monotonic() + self._ttl)


cache_manager: AsyncIdempotencyCache = AsyncIdempotencyCache(
    ttl=10.0, cleanup_interval=30.0
)


def generate_idempotency_key(
    dto: BaseModel,
    exclude: set[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Return a SHA-256 hex key for the DTO's JSON form and the extra values.

    The DTO and extra are hashed side by side, so an extra entry never overwrites a
    DTO field of the same name. Extra values must be JSON-serializable. SecretStr
    fields are masked in JSON mode and do not distinguish keys.
    """
    return _hash_payload(
        {
            "dto": dto.model_dump(mode="json", exclude=exclude),
            "extra": {} if extra is None else extra,
        }
    )


def _hash_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


# Secret values enter the key through an HMAC under this per-process salt, so a
# key seen in a 409 response or a log cannot be brute-forced back to a password.
_SECRET_SALT = secrets.token_bytes(32)


class _UnkeyableError(Exception):
    """The value is not request data, such as a Request or a session."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _key_form(value: object, exclude: set[str] | None) -> Any:
    """Return value as JSON-ready data for an idempotency key.

    Raise _UnkeyableError when pydantic cannot serialize value.
    """
    if isinstance(value, BaseModel):
        return _key_form(value.model_dump(exclude=exclude), None)
    if isinstance(value, SecretStr | SecretBytes | Secret):
        revealed = _canonical_json(_key_form(value.get_secret_value(), exclude))
        return hmac.new(_SECRET_SALT, revealed.encode(), "sha256").hexdigest()
    if isinstance(value, bytes | bytearray):
        return hashlib.sha256(value).hexdigest()
    if isinstance(value, list | tuple):
        return [_key_form(item, exclude) for item in value]
    if isinstance(value, set | frozenset):
        return sorted((_key_form(item, exclude) for item in value), key=_canonical_json)
    if isinstance(value, dict):
        if all(isinstance(k, str) for k in value):
            return {k: _key_form(v, exclude) for k, v in value.items()}
        pairs = (
            [_key_form(k, exclude), _key_form(v, exclude)] for k, v in value.items()
        )
        return sorted(pairs, key=_canonical_json)
    if isinstance(value, Iterator):
        # Serializing would drain it and hand the function an empty iterator.
        raise _UnkeyableError(type(value).__qualname__)
    try:
        return to_jsonable_python(value)
    except ValueError as exc:
        raise _UnkeyableError(type(value).__qualname__) from exc


def _contains_model(value: object) -> bool:
    if isinstance(value, BaseModel):
        return True
    if isinstance(value, list | tuple | set | frozenset):
        return any(_contains_model(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_model(item) for item in value.values())
    return False


def _call_key_arguments(
    arguments: Mapping[str, object], exclude: set[str] | None
) -> dict[str, Any] | None:
    """Return the key form of the arguments that identify a call.

    Return None, so the caller runs uncached, when no argument holds a model or
    when an argument that holds one cannot be serialized.
    """
    keyed: dict[str, Any] = {}
    has_model = False
    for name, value in arguments.items():
        holds_model = _contains_model(value)
        try:
            keyed[name] = _key_form(value, exclude)
        except _UnkeyableError:
            if holds_model:
                return None
            continue
        has_model = has_model or holds_model
    return keyed if has_model else None


def idempotent[**P, R](
    exclude: set[str] | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Coroutine[Any, Any, R]]]:
    """Run the decorated coroutine function once per distinct call via cache_manager.

    The key is built from every bound argument, defaults applied, so a body, the
    path and query parameters and dependency results such as the current user all
    count:

    - a model is dumped with `exclude` applied to it, also when it sits in a
      list, tuple, set or dict argument (not to models nested in its fields);
    - secret values count by their secret, through a salted HMAC; bytes by their
      SHA-256; sets in sorted order; everything else in pydantic's JSON form;
    - an argument that pydantic cannot serialize (Request, Response, WebSocket,
      BackgroundTasks, sessions, callables) or that is an iterator, which
      serializing would drain, is skipped, so it must not be what tells two
      calls apart.

    The function runs uncached when no argument holds a model, or when an
    argument that holds one cannot be serialized. The key also holds the
    function's module and qualified name, so two endpoints that receive the same
    arguments do not share a result. A concurrent duplicate gets HTTP 409.
    """

    def decorator(
        func: Callable[P, Awaitable[R]],
    ) -> Callable[P, Coroutine[Any, Any, R]]:
        func_id = f"{func.__module__}.{func.__qualname__}"
        # Only parameter names and defaults are needed. FORWARDREF keeps an
        # annotation that names a later definition from raising NameError here.
        signature = inspect.signature(
            func, annotation_format=annotationlib.Format.FORWARDREF
        )

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            arguments = _call_key_arguments(bound.arguments, exclude)
            if arguments is None:
                return await func(*args, **kwargs)

            key = _hash_payload({"func": func_id, "args": arguments})
            result: R = await cache_manager.process(key, lambda: func(*args, **kwargs))
            return result

        return wrapper

    return decorator


class QueryIdempotencyDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    endpoint: str
    params: dict[str, Any] = Field(default_factory=dict)
