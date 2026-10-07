"""Command-line entry point that runs the application under uvicorn.

Reference FastAPI Boilerplate from https://github.com/teamhide/fastapi-boilerplate.
"""

import os

import click
import uvicorn


@click.command()
@click.option(
    "--env",
    type=click.Choice(["prod", "dev", "local"], case_sensitive=False),
    default="local",
)
@click.option("--debug", is_flag=True, default=False)
def main(env: str, debug: bool) -> None:
    os.environ["ENV"] = env
    if debug:
        # Without the flag the environment's own DEBUG setting applies.
        os.environ["DEBUG"] = "true"
    # Imported only after ENV is set: the settings class is chosen from ENV, and
    # uvicorn's reload and worker processes inherit this environment.
    from app.core.config.config import get_config

    config = get_config()
    uvicorn.run(
        "app.server:init_app",
        factory=True,
        host=config.APP_HOST,
        port=config.APP_PORT,
        reload=env != "prod",
        workers=1 if env != "prod" else config.WORKERS,
    )


if __name__ == "__main__":
    main()
