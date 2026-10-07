import logging
from typing import Any

logger = logging.getLogger(__name__)


class Singleton(type):
    """Return an object that can be used as a singleton"""

    _instances: dict[type, Any] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            logger.debug("Singleton instance %s not found, creating it", cls.__name__)
            cls._instances[cls] = super().__call__(*args, **kwargs)
        logger.debug("Returning singleton instance %s", cls.__name__)
        return cls._instances[cls]
