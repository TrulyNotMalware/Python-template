import os
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.exception.configuration_exception import (
    ConfigurationEnum,
    ConfigurationError,
    ConfigurationException,
)
from app.core.exception.error_base import ArgumentError, ErrorCode


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        validate_assignment=True,
    )

    ENV: str = "local"
    DEBUG: bool = True
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8080
    DATABASE_URL: str = "sqlite+aiosqlite://"
    DATABASE_HOST: str | None = None
    DATABASE_PORT: str | None = None
    DATABASE_USER: str | None = None
    DATABASE_PASSWORD: str | None = None
    DATABASE_NAME: str | None = None
    WORKERS: int = 1

    @model_validator(mode="after")
    def set_database_url(self) -> Self:
        if (
            not self.DATABASE_URL
            and self.DATABASE_USER
            and self.DATABASE_PASSWORD
            and self.DATABASE_HOST
            and self.DATABASE_PORT
            and self.DATABASE_NAME
        ):
            self.DATABASE_URL = (
                f"mariadb+aiomysql://"
                f"{self.DATABASE_USER}:{self.DATABASE_PASSWORD}"
                f"@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
            )
        return self


class LocalConfig(Config):
    model_config = SettingsConfigDict(env_file=".env.local")

    ENV: str = "local"
    DEBUG: bool = True
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8080
    DATABASE_URL: str = "sqlite+aiosqlite://"


class DevConfig(Config):
    model_config = SettingsConfigDict(env_file=".env.dev")

    ENV: str = "dev"
    DEBUG: bool = True
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8080
    DATABASE_USER: str = "YOUR_USER"
    DATABASE_PASSWORD: str = os.environ.get(
        "DATABASE_PASSWORD", default="YOUR_PASSWORD"
    )
    DATABASE_HOST: str = "YOUR_HOST"
    DATABASE_NAME: str = "YOUR_DATABASE_NAME"
    DATABASE_PORT: str = "3306"
    DATABASE_URL: str = ""


class ProdConfig(Config):
    model_config = SettingsConfigDict(env_file=".env.prod")

    ENV: str = "prod"
    DEBUG: bool = False
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8080
    DATABASE_USER: str = "YOUR_USER"
    DATABASE_PASSWORD: str = os.environ.get(
        "DATABASE_PASSWORD", default="YOUR_PASSWORD"
    )
    DATABASE_HOST: str = "YOUR_HOST"
    DATABASE_NAME: str = "YOUR_DATABASE_NAME"
    DATABASE_PORT: str = "3306"
    DATABASE_URL: str = ""
    WORKERS: int = 4


class ConfigLoader:
    def __init__(self, env: str) -> None:
        self.env = env
        self.config = self.__get_config()

    def __get_config(self) -> Config:
        config_map: dict[str, type[Config]] = {
            "local": LocalConfig,
            "dev": DevConfig,
            "prod": ProdConfig,
        }
        config_cls = config_map.get(self.env)
        if config_cls is None:
            error_code: ErrorCode = ConfigurationError(
                error=ConfigurationEnum.NOT_A_VALID_CONFIGURATION_NAME
            )
            argument_error: ArgumentError = ArgumentError(
                field_name="env",
                value=self.env,
                reason=f"env type {self.env} is not supported",
            )
            raise ConfigurationException(
                error_code=error_code, argument_errors=[argument_error]
            )
        return config_cls()


loader = ConfigLoader(env=os.getenv("ENV", "local"))
