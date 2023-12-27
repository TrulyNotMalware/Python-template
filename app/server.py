from typing import List

from fastapi import FastAPI, Depends
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from api.root_router import root_router
from app.core.db.session import init_tables
from app.core.exception.error_base import CustomException
from app.core.exception.exception_handlers import custom_exception_handler
from app.core.fastapi.logging import Logging
from app.core.fastapi.middlewares import ResponseLogMiddleware
from app.core.fastapi.middlewares.sqlalchemy import SQLAlchemyMiddleware


def init_routers(app: FastAPI) -> None:
    app.include_router(router=root_router)


def init_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(CustomException, custom_exception_handler)


def init_middleware() -> List[Middleware]:
    middlewares = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        ),
        Middleware(SQLAlchemyMiddleware),
        Middleware(ResponseLogMiddleware)
    ]
    return middlewares


def init_app() -> FastAPI:
    app = FastAPI(
        title="Python MicroService App",
        description="Microservice templates",
        version="0.0.1",
        docs_url="/swagger_ui",
        redoc_url="/redoc",
        dependencies=[Depends(Logging)],
        middleware=init_middleware()
    )
    init_routers(app=app)
    init_exception_handlers(app=app)
    return app


app = init_app()


@app.on_event("startup")
async def startup() -> None:
    await init_tables()
