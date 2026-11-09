from fastapi import APIRouter


async def require_auth() -> None:
    return None


router = APIRouter(prefix="/auth")
