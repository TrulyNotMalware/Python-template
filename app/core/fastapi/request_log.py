"""Make the application's request log lines visible.

``ResponseLogMiddleware`` writes one DEBUG line per response to a logger below
``app``. uvicorn configures only its own loggers, so without this setup those
lines, and every other ``app.*`` record below WARNING, are dropped.
"""

import logging


def configure_logging(*, debug: bool) -> None:
    """Set the ``app`` logger level and give it a stderr handler if none exists.

    An existing handler on ``app`` or on the root logger (``--log-config``, a test
    runner) is left alone, so records are not written twice.
    """
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    if app_logger.handlers or logging.getLogger().handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    app_logger.addHandler(handler)
