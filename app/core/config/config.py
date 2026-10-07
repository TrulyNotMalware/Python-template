"""Settings per environment, selected by the ``ENV`` environment variable."""

import os
from functools import lru_cache
from typing import ClassVar, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

from app.core.exception.configuration_exception import (
    ConfigurationEnum,
    ConfigurationError,
    ConfigurationException,
)
from app.core.exception.error_base import ArgumentError


class Config(BaseSettings):
    # Each concrete class names its own env_file. env_ignore_empty: a blank
    # "KEY=" line counts as unset, so a copied .env.example starts, and a blank
    # required value is reported as missing.
    model_config = SettingsConfigDict(extra="ignore", env_ignore_empty=True)

    # A class constant, not a setting: get_config() picks the class from the ENV
    # environment variable, and no env file can make it name another one.
    ENV: ClassVar[str] = "local"
    DEBUG: bool = False
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8080
    WORKERS: int = 1
    # Database URLs can carry a password, so they are left out of repr().
    DATABASE_URL: str = Field(default="sqlite+aiosqlite://", repr=False)
    # None reuses the writer engine for reads.
    DATABASE_READ_URL: str | None = Field(default=None, repr=False)
    MONGO_URL: SecretStr | None = None
    MONGO_DATABASE: str | None = None
    # A JSON list. With "*" in it, CORS responses never allow credentials.
    CORS_ALLOW_ORIGINS: list[str] = []


class LocalConfig(Config):
    model_config = SettingsConfigDict(env_file=".env.local")

    ENV: ClassVar[str] = "local"
    DEBUG: bool = True


class ServerConfig(Config):
    """Settings of a deployed environment; the database URL is built from parts."""

    DATABASE_USER: str
    DATABASE_PASSWORD: SecretStr
    DATABASE_HOST: str
    DATABASE_PORT: int
    DATABASE_NAME: str

    @model_validator(mode="after")
    def assemble_database_url(self) -> Self:
        # URL.create escapes characters such as "@", "/" and "#" in the password.
        self.DATABASE_URL = URL.create(
            drivername="mariadb+aiomysql",
            username=self.DATABASE_USER,
            password=self.DATABASE_PASSWORD.get_secret_value(),
            host=self.DATABASE_HOST,
            port=self.DATABASE_PORT,
            database=self.DATABASE_NAME,
        ).render_as_string(hide_password=False)
        return self


class DevConfig(ServerConfig):
    model_config = SettingsConfigDict(env_file=".env.dev")

    ENV: ClassVar[str] = "dev"
    DEBUG: bool = True


class ProdConfig(ServerConfig):
    model_config = SettingsConfigDict(env_file=".env.prod")

    ENV: ClassVar[str] = "prod"
    DEBUG: bool = False
    APP_HOST: str = "0.0.0.0"  # noqa: S104  the container's port mapping limits access
    WORKERS: int = 4


@lru_cache
def get_config() -> Config:
    """Return the settings of the environment named by ``ENV``, read once."""
    config_classes: dict[str, type[Config]] = {
        "local": LocalConfig,
        "dev": DevConfig,
        "prod": ProdConfig,
    }
    env = os.environ.get("ENV", "local")
    config_cls = config_classes.get(env)
    if config_cls is None:
        raise ConfigurationException(
            error_code=ConfigurationError(
                error=ConfigurationEnum.NOT_A_VALID_CONFIGURATION_NAME
            ),
            argument_errors=[
                ArgumentError(
                    field_name="env",
                    value=env,
                    reason=f"env type {env} is not supported",
                )
            ],
        )
    return config_cls()
