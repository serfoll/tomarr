from importlib.metadata import version

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/system")


class SystemStatus(BaseModel):
    version: str


@router.get("/status", response_model=SystemStatus)
def get_status() -> SystemStatus:
    return SystemStatus(version=version("tomarr"))
