import os

from pydantic.v1 import BaseSettings

from app.core.exception.configuration_exception import ConfigurationException, ConfigurationError, ConfigurationEnum
from app.core.exception.error_base import ErrorCode, ArgumentError

"""
Default app server configuration
"""


class LocalConfig(BaseSettings):
    ENV: str = "local"  # Default is local.
    DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8080
    DATABASE_URL = "sqlite+aiosqlite://"


class DevConfig(LocalConfig):
    ENV: str = "dev"
    DEBUG: bool = True
    DATABASE_USER = "YOUR_USER"
    DATABASE_PASSWORD = "YOUR_PASSWORD"
    DATABASE_HOST = "YOUR_HOST"
    DATABASE_NAME = "YOUR_DATABASE_NAME"
    DATABASE_PORT = "YOUR_DATABASE_PORT"
    DATABASE_URL = f"mariadb+aiomysql://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"


class ProdConfig(LocalConfig):
    ENV: str = "prod"
    DEBUG: bool = False
    DATABASE_USER = "YOUR_USER"
    DATABASE_PASSWORD = "YOUR_PASSWORD"
    DATABASE_HOST = "YOUR_HOST"
    DATABASE_NAME = "YOUR_DATABASE_NAME"
    DATABASE_PORT = "YOUR_DATABASE_PORT"
    DATABASE_URL = f"mariadb+aiomysql://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
    WORKERS = 1


class ConfigLoader:

    def __init__(self, env: str):
        self.env = env
        self.config = self.__get_config()

    def refresh(self):
        self.env = os.environ.get("ENV")
        self.config = self.__get_config()

    def __get_config(self):
        configs = {
            "local": LocalConfig(),
            "dev": DevConfig(),
            "prod": ProdConfig()
        }
        if configs.get(self.env) is None:
            error_code: ErrorCode = ConfigurationError(error=ConfigurationEnum.NOT_A_VALID_CONFIGURATION_NAME)
            argument_error: ArgumentError = ArgumentError(
                field_name="env",
                value=self.env,
                reason=f"env type {self.env} is not supported"
            )
            raise ConfigurationException(error_code=error_code, argument_errors=[argument_error])
        else:
            return configs[self.env]


loader: ConfigLoader = ConfigLoader(env=os.getenv("ENV", "local"))
