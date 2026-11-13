import asyncio
import secrets
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from tomarr.core.auth import (
    DUMMY_HASH,
    SessionSigner,
    hash_password,
    session_fingerprint,
    verify_password,
)
from tomarr.core.errors import SetupAlreadyDone
from tomarr.services.settings import SettingsService, registry

SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
MIN_PASSWORD_LENGTH = 8
MAX_CREDENTIAL_LENGTH = 256
# Each Argon2 call holds about 64 MiB and a worker thread, and login and setup are open routes.
MAX_CONCURRENT_HASHES = 2


class Credentials(BaseModel):
    model_config = ConfigDict(frozen=True)

    username: str
    password_hash: str = Field(repr=False)
    session_secret: str = Field(repr=False)


CREDENTIALS = registry.declare("auth.credentials", TypeAdapter(Credentials | None), None)
LOCAL_BYPASS = registry.declare("auth.local_bypass", TypeAdapter(bool), False)
RESET_CONSUMED = registry.declare("auth.reset_consumed", TypeAdapter(bool), False)


class AuthService:
    def __init__(self, settings: SettingsService, *, reset_requested: bool) -> None:
        self._settings = settings
        self._reset_requested = reset_requested
        # The container runs one uvicorn process, so a process-local lock is enough.
        self._setup_lock = asyncio.Lock()
        self._hashing = asyncio.Semaphore(MAX_CONCURRENT_HASHES)

    async def setup_required(self) -> bool:
        if await self._settings.get(CREDENTIALS) is None:
            return True
        return self._reset_requested and not await self._settings.get(RESET_CONSUMED)

    async def setup(self, username: str, password: str) -> str:
        async with self._setup_lock:
            if not await self.setup_required():
                raise SetupAlreadyDone
            credentials = Credentials(
                username=username,
                password_hash=await self._argon2(hash_password, password),
                session_secret=secrets.token_urlsafe(32),
            )
            # The marker goes first: if the credentials write then fails, the window is closed
            # and the old password still works, rather than the window staying open for anyone.
            if self._reset_requested:
                await self._settings.set(RESET_CONSUMED, True)
            await self._settings.set(CREDENTIALS, credentials)
        return _issue_session(credentials)

    async def rearm_reset(self) -> None:
        """Called at startup, so removing the variable lets the next set open a new window."""
        if not self._reset_requested and await self._settings.get(RESET_CONSUMED):
            await self._settings.set(RESET_CONSUMED, False)

    async def login(self, username: str, password: str) -> str | None:
        credentials = await self._settings.get(CREDENTIALS)
        if credentials is None:
            await self._argon2(verify_password, password, DUMMY_HASH)
            return None
        password_ok = await self._argon2(verify_password, password, credentials.password_hash)
        if not (_same(username, credentials.username) and password_ok):
            return None
        return _issue_session(credentials)

    async def verify_session(self, token: str) -> bool:
        credentials = await self._settings.get(CREDENTIALS)
        if credentials is None:
            return False
        presented = SessionSigner(credentials.session_secret).read(token, SESSION_MAX_AGE_SECONDS)
        return presented is not None and _same(presented, _fingerprint(credentials))

    async def local_bypass_enabled(self) -> bool:
        return await self._settings.get(LOCAL_BYPASS)

    async def _argon2[*Args, R](self, work: Callable[[*Args], R], *args: *Args) -> R:
        async with self._hashing:
            return await asyncio.to_thread(work, *args)


def _same(left: str, right: str) -> bool:
    return secrets.compare_digest(left.encode(), right.encode())


def _fingerprint(credentials: Credentials) -> str:
    return session_fingerprint(
        credentials.session_secret, credentials.username, credentials.password_hash
    )


def _issue_session(credentials: Credentials) -> str:
    return SessionSigner(credentials.session_secret).issue(_fingerprint(credentials))
