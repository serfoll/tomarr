import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI

from tomarr.api import auth, system
from tomarr.core.config import config_dir, load_settings
from tomarr.core.database import Database, create_database
from tomarr.core.logging import close_logging, configure_logging
from tomarr.core.migrations import upgrade_to_head
from tomarr.services.auth import AuthService
from tomarr.services.settings import SettingsService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    directory = config_dir()
    settings = load_settings(directory)
    configure_logging(settings.log.level, directory / "logs", [settings.auth.apikey])
    database: Database | None = None
    try:
        try:
            path = directory / "tomarr.db"
            await asyncio.to_thread(upgrade_to_head, path)
            database = create_database(path)
            # The pragmas run on connect, so one connection here turns WAL on from boot and makes
            # a broken database stop startup instead of failing the first request.
            async with database.engine.connect():
                pass
        except Exception:
            logger.exception("Database startup failed")
            raise
        app.state.database = database
        app.state.settings = settings
        app.state.auth = AuthService(SettingsService(database.session_factory))
        if await app.state.auth.setup_required():
            logger.warning(
                "No credentials are set. Open Tomarr in a browser to create the first login."
            )
        yield
    finally:
        try:
            if database is not None:
                await database.dispose()
        finally:
            close_logging()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    protected = APIRouter(dependencies=[Depends(auth.require_auth)])
    protected.include_router(system.router)
    app.include_router(protected, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(system.public_router, prefix="/api/v1")
    return app
