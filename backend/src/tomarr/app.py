import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from tomarr.api import system
from tomarr.core.config import config_dir, load_settings
from tomarr.core.database import Database, create_database
from tomarr.core.logging import close_logging, configure_logging
from tomarr.core.migrations import upgrade_to_head


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    directory = config_dir()
    settings = load_settings(directory)
    configure_logging(settings.log.level, directory / "logs", [settings.auth.apikey])
    database: Database | None = None
    try:
        path = directory / "tomarr.db"
        await asyncio.to_thread(upgrade_to_head, path)
        database = create_database(path)
        app.state.database = database
        yield
    finally:
        if database is not None:
            await database.dispose()
        close_logging()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.include_router(system.router, prefix="/api/v1")
    return app
