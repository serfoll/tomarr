from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from tomarr.api import system
from tomarr.core.config import config_dir, load_settings
from tomarr.core.logging import close_logging, configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    directory = config_dir()
    settings = load_settings(directory)
    configure_logging(settings.log.level, directory / "logs", [settings.auth.apikey])
    try:
        yield
    finally:
        close_logging()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.include_router(system.router, prefix="/api/v1")
    return app
