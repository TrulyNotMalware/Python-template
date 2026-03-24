import logging
from typing import Any

logger = logging.getLogger(__name__)


class Singleton(type):
    """Return an object that can be used as a singleton"""

    _instances: dict[type, Any] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            logger.info(f"Singleton Instance {cls.__name__} Not found. create.")
            cls._instances[cls] = super().__call__(*args, **kwargs)
        logger.info(f"Return Singleton instance {cls.__name__}")
        return cls._instances[cls]
