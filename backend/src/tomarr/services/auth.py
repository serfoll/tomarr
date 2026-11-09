import asyncio
import secrets

from pydantic import BaseModel, ConfigDict, TypeAdapter

from tomarr.core.auth import (
    DUMMY_HASH,
    SessionSigner,
    hash_password,
    password_fingerprint,
    verify_password,
)
from tomarr.services.settings import SettingsService, registry

SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
MIN_PASSWORD_LENGTH = 8
MAX_CREDENTIAL_LENGTH = 256


class Credentials(BaseModel):
    model_config = ConfigDict(frozen=True)

    username: str
    password_hash: str
    session_secret: str


CREDENTIALS = registry.declare("auth.credentials", TypeAdapter(Credentials | None), None)
LOCAL_BYPASS = registry.declare("auth.local_bypass", TypeAdapter(bool), False)


class SetupAlreadyDone(Exception):
    pass


class AuthService:
    def __init__(self, settings: SettingsService) -> None:
        self._settings = settings
        # The container runs one uvicorn process, so a process-local lock is enough.
        self._setup_lock = asyncio.Lock()

    async def setup_required(self) -> bool:
        return await self._settings.get(CREDENTIALS) is None

    async def setup(self, username: str, password: str) -> str:
        async with self._setup_lock:
            if not await self.setup_required():
                raise SetupAlreadyDone
            credentials = Credentials(
                username=username,
                password_hash=await asyncio.to_thread(hash_password, password),
                session_secret=secrets.token_urlsafe(32),
            )
            await self._settings.set(CREDENTIALS, credentials)
        return _issue_session(credentials)

    async def login(self, username: str, password: str) -> str | None:
        credentials = await self._settings.get(CREDENTIALS)
        if credentials is None:
            await asyncio.to_thread(verify_password, password, DUMMY_HASH)
            return None
        password_ok = await asyncio.to_thread(verify_password, password, credentials.password_hash)
        if not (_same(username, credentials.username) and password_ok):
            return None
        return _issue_session(credentials)

    async def verify_session(self, token: str) -> bool:
        credentials = await self._settings.get(CREDENTIALS)
        if credentials is None:
            return False
        payload = SessionSigner(credentials.session_secret).read(token, SESSION_MAX_AGE_SECONDS)
        if payload is None:
            return False
        return _same(payload.username, credentials.username) and _same(
            payload.fingerprint, password_fingerprint(credentials.password_hash)
        )

    async def local_bypass_enabled(self) -> bool:
        return await self._settings.get(LOCAL_BYPASS)


def _same(left: str, right: str) -> bool:
    return secrets.compare_digest(left.encode(), right.encode())


def _issue_session(credentials: Credentials) -> str:
    return SessionSigner(credentials.session_secret).issue(
        credentials.username, password_fingerprint(credentials.password_hash)
    )
