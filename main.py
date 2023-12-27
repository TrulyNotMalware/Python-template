import os

import click
import uvicorn

from app.core.config.config import loader

"""
Reference FastAPI Boilerplate from https://github.com/teamhide/fastapi-boilerplate. 
"""

@click.command()
@click.option(
    "--env",
    type=click.Choice(["prod", "dev", "local"], case_sensitive=False),
    default="local",
)
@click.option(
    "--debug",
    type=click.BOOL,
    is_flag=True,
    default=False
)
def main(env: str, debug: bool):
    os.environ["ENV"] = env
    os.environ["DEBUG"] = str(debug)
    loader.refresh()
    uvicorn.run(
        app="app.server:app",
        host=loader.config.APP_HOST,
        port=loader.config.APP_PORT,
        reload=True if env != "prod" else False,
        workers=1 if env != "prod" else loader.config.WORKERS
    )


if __name__ == "__main__":
    main()
