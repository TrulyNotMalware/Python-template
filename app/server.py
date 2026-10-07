"""Application factory. Serve it with ``uvicorn app.server:init_app --factory``."""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# Importing the model module registers its tables on Base.metadata; without it
# init_tables() runs create_all() on an empty metadata and creates no table.
import app.user.model.user  # noqa: F401
from api.root_router import root_router
from app.core.cache.idempotency_cache import cache_manager
from app.core.config.config import Config, get_config
from app.core.db.nosql.client import create_mongo_client
from app.core.db.session import dispose_engines, init_engines, init_tables
from app.core.exception.error_base import CustomException
from app.core.exception.exception_handlers import (
    custom_exception_handler,
    http_exception_handler,
)
from app.core.fastapi.middlewares import ResponseLogMiddleware, SQLAlchemyMiddleware
from app.core.fastapi.request_log import configure_logging
from app.core.utils.tasks import TaskOwner


def init_routers(application: FastAPI) -> None:
    application.include_router(router=root_router)


def init_exception_handlers(application: FastAPI) -> None:
    application.exception_handler(CustomException)(custom_exception_handler)
    application.exception_handler(StarletteHTTPException)(http_exception_handler)


def init_middleware(config: Config) -> list[Middleware]:
    origins = config.CORS_ALLOW_ORIGINS
    return [
        Middleware(
            CORSMiddleware,
            allow_origins=origins,
            # A wildcard origin with credentials would grant every site
            # credentialed access.
            allow_credentials="*" not in origins,
            allow_methods=["*"],
            allow_headers=["*"],
        ),
        Middleware(SQLAlchemyMiddleware),
        Middleware(ResponseLogMiddleware),
    ]


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[dict[str, object]]:
    config = get_config()
    async with AsyncExitStack() as cleanup:
        # Callbacks run in reverse: tasks, then MongoDB, then the SQL engines.
        init_engines(config.DATABASE_URL, config.DATABASE_READ_URL)
        cleanup.push_async_callback(dispose_engines)
        await init_tables()

        mongo: AsyncMongoClient[dict[str, Any]] | None = None
        mongo_db: AsyncDatabase[dict[str, Any]] | None = None
        if config.MONGO_URL is not None:
            mongo = create_mongo_client(config.MONGO_URL.get_secret_value())
            cleanup.push_async_callback(mongo.close)
            if config.MONGO_DATABASE is not None:
                mongo_db = mongo.get_database(config.MONGO_DATABASE)

        owner = TaskOwner()
        cleanup.push_async_callback(owner.close)
        owner.spawn(cache_manager.evict_loop(), name="idempotency-evict")

        yield {"tasks": owner, "mongo": mongo, "mongo_db": mongo_db}


def init_app() -> FastAPI:
    config = get_config()
    configure_logging(debug=config.DEBUG)
    # openapi_url=None is what closes /openapi.json; docs_url alone hides only
    # the Swagger page.
    is_prod = config.ENV == "prod"
    application = FastAPI(
        lifespan=lifespan,
        title="Python MicroService App",
        description="Microservice templates",
        version="0.0.1",
        docs_url=None if is_prod else "/swagger_ui",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
        middleware=init_middleware(config),
    )
    init_routers(application=application)
    init_exception_handlers(application=application)
    return application
