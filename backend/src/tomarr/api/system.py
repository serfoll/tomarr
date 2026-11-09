from importlib.metadata import version
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

APP_VERSION = version("tomarr")

router = APIRouter(prefix="/system")
public_router = APIRouter(prefix="/system")


class SystemStatus(BaseModel):
    version: str


class Health(BaseModel):
    status: Literal["ok"]


@router.get("/status", response_model=SystemStatus)
def get_status() -> SystemStatus:
    return SystemStatus(version=APP_VERSION)


@public_router.get("/health", response_model=Health)
def get_health() -> Health:
    return Health(status="ok")


# Healthchecks such as `curl -I` and `wget --spider` send HEAD, which a GET route does not answer.
@public_router.head("/health", include_in_schema=False)
def head_health() -> Response:
    return Response(status_code=status.HTTP_200_OK)
