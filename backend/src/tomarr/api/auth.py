import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from tomarr.core.auth import is_local_address
from tomarr.core.config import Settings
from tomarr.services.auth import (
    MAX_CREDENTIAL_LENGTH,
    MIN_PASSWORD_LENGTH,
    SESSION_MAX_AGE_SECONDS,
    AuthService,
    SetupAlreadyDone,
)

SESSION_COOKIE = "tomarr_session"
# Any of these means a proxy is in front, so the peer address says nothing about the client.
PROXY_HEADER_PREFIXES = ("x-forwarded-", "forwarded")
PROXY_HEADERS = frozenset({"x-real-ip", "cf-connecting-ip", "true-client-ip", "x-client-ip", "via"})
# A search, not a match: the value needs one non-whitespace character anywhere.
NOT_BLANK = r"\S"

router = APIRouter(prefix="/auth")

api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)


class AuthStatus(BaseModel):
    setup_required: bool
    authenticated: bool


def get_auth_service(request: Request) -> AuthService:
    auth: AuthService = request.app.state.auth
    return auth


ApiKey = Annotated[str | None, Depends(api_key_header)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
Username = Annotated[str, Form(min_length=1, max_length=MAX_CREDENTIAL_LENGTH, pattern=NOT_BLANK)]
LoginPassword = Annotated[str, Form(min_length=1, max_length=MAX_CREDENTIAL_LENGTH)]
SetupPassword = Annotated[
    str,
    Form(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_CREDENTIAL_LENGTH, pattern=NOT_BLANK),
]


async def is_authenticated(request: Request, api_key: str | None, auth: AuthService) -> bool:
    settings: Settings = request.app.state.settings
    if api_key is not None and secrets.compare_digest(
        api_key.encode(), settings.auth.apikey.encode()
    ):
        return True
    if _from_local_peer(request) and await auth.local_bypass_enabled():
        return True
    token = request.cookies.get(SESSION_COOKIE)
    return token is not None and await auth.verify_session(token)


async def require_auth(request: Request, api_key: ApiKey, auth: AuthServiceDep) -> None:
    if not await is_authenticated(request, api_key, auth):
        raise api_key_header.make_not_authenticated_error()


def _from_local_peer(request: Request) -> bool:
    if any(
        name.startswith(PROXY_HEADER_PREFIXES) or name in PROXY_HEADERS for name in request.headers
    ):
        return False
    return request.client is not None and is_local_address(request.client.host)


@router.get("/status", response_model=AuthStatus)
async def get_status(request: Request, api_key: ApiKey, auth: AuthServiceDep) -> AuthStatus:
    return AuthStatus(
        setup_required=await auth.setup_required(),
        authenticated=await is_authenticated(request, api_key, auth),
    )


@router.post("/setup", status_code=status.HTTP_204_NO_CONTENT)
async def setup(
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    username: Username,
    password: SetupPassword,
) -> None:
    try:
        token = await auth.setup(username, password)
    except SetupAlreadyDone:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Setup is already done. Log in with the existing username."
        ) from None
    _set_session_cookie(request, response, token)


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
async def login(
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    username: Username,
    password: LoginPassword,
) -> None:
    token = await auth.login(username, password)
    if token is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Wrong username or password. Check both and try again."
        )
    _set_session_cookie(request, response, token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )


def _set_session_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE_SECONDS,
        path="/",
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
