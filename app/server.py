from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from api.root_router import root_router
from app.core.config.config import loader
from app.core.db.session import init_engines, init_tables
from app.core.exception.error_base import CustomException
from app.core.exception.exception_handlers import custom_exception_handler
from app.core.fastapi.logging import Logging
from app.core.fastapi.middlewares import ResponseLogMiddleware
from app.core.fastapi.middlewares.sqlalchemy import SQLAlchemyMiddleware


def init_routers(application: FastAPI) -> None:
    application.include_router(router=root_router)


def init_exception_handlers(application: FastAPI) -> None:
    application.add_exception_handler(CustomException, custom_exception_handler)


def init_middleware() -> list[Middleware]:
    middlewares = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        ),
        Middleware(SQLAlchemyMiddleware),
        Middleware(ResponseLogMiddleware),
    ]
    return middlewares


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
    init_engines(database_url=loader.config.DATABASE_URL)
    await init_tables()
    yield


def init_app() -> FastAPI:
    application = FastAPI(
        lifespan=lifespan,
        title="Python MicroService App",
        description="Microservice templates",
        version="0.0.1",
        docs_url="/swagger_ui",
        redoc_url="/redoc",
        dependencies=[Depends(Logging)],
        middleware=init_middleware(),
    )
    init_routers(application=application)
    init_exception_handlers(application=application)
    return application


app = init_app()
