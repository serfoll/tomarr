from fastapi import FastAPI

from tomarr.api import system


def create_app() -> FastAPI:
    app = FastAPI()
    app.include_router(system.router, prefix="/api/v1")
    return app
