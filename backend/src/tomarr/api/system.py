from importlib.metadata import version
from typing import Literal

from fastapi import APIRouter
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
