import asyncio
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from tomarr.core.auth import SessionSigner, hash_password, session_fingerprint, verify_password
from tomarr.core.database import Database, create_database
from tomarr.core.errors import SetupAlreadyDone
from tomarr.core.migrations import upgrade_to_head
from tomarr.services import auth as auth_module
from tomarr.services.auth import (
    CREDENTIALS,
    LOCAL_BYPASS,
    AuthService,
    Credentials,
)
from tomarr.services.settings import SettingsService, registry

USERNAME = "reader"
PASSWORD = "correct horse battery"
# The source string of core.auth.DUMMY_HASH. Logging in with it must never succeed.
DUMMY_SOURCE_PASSWORD = "tomarr-dummy-password"


@pytest.fixture(scope="module")
def stored_hash() -> str:
    return hash_password(PASSWORD)


@pytest.fixture
def settings(database: Database) -> SettingsService:
    return SettingsService(database.session_factory)


@pytest.fixture
def auth(settings: SettingsService) -> AuthService:
    return AuthService(settings)


@pytest.fixture
async def seeded(settings: SettingsService, stored_hash: str) -> Credentials:
    credentials = Credentials(
        username=USERNAME, password_hash=stored_hash, session_secret="seeded-secret"
    )
    await settings.set(CREDENTIALS, credentials)
    return credentials


@pytest.fixture
def verify_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def counting_verify(password: str, password_hash: str) -> bool:
        calls.append(password_hash)
        return verify_password(password, password_hash)

    monkeypatch.setattr(auth_module, "verify_password", counting_verify)
    return calls


@pytest.fixture
def peak_argon2_calls(monkeypatch: pytest.MonkeyPatch) -> Callable[[], int]:
    lock = threading.Lock()
    running = 0
    peak = 0

    def tracked[**P, R](work: Callable[P, R]) -> Callable[P, R]:
        def slow(*args: P.args, **kwargs: P.kwargs) -> R:
            nonlocal running, peak
            with lock:
                running += 1
                peak = max(peak, running)
            time.sleep(0.05)
            with lock:
                running -= 1
            return work(*args, **kwargs)

        return slow

    monkeypatch.setattr(auth_module, "hash_password", tracked(hash_password))
    monkeypatch.setattr(auth_module, "verify_password", tracked(verify_password))
    return lambda: peak


async def stored_credentials_json(database: Database) -> str:
    async with database.session_factory() as session:
        result = await session.execute(
            text("SELECT value FROM setting WHERE key = 'auth.credentials'")
        )
        return str(result.scalar_one())


def test_keys_are_declared_on_the_registry() -> None:
    # SettingsRegistry.keys() is not a dict method, the registry is not iterable.
    names = {key.name for key in registry.keys()}  # noqa: SIM118

    assert {"auth.credentials", "auth.local_bypass"} <= names


async def test_setup_required_is_true_on_a_fresh_database(auth: AuthService) -> None:
    assert await auth.setup_required() is True


async def test_setup_required_is_false_after_setup(auth: AuthService) -> None:
    await auth.setup(USERNAME, PASSWORD)

    assert await auth.setup_required() is False


async def test_setup_stores_a_hash_and_a_secret_and_returns_a_valid_session(
    auth: AuthService, settings: SettingsService, database: Database
) -> None:
    token = await auth.setup(USERNAME, PASSWORD)

    credentials = await settings.get(CREDENTIALS)
    assert credentials is not None
    assert credentials.username == USERNAME
    is_argon2 = credentials.password_hash.startswith("$argon2")
    long_secret = len(credentials.session_secret) >= 43
    assert is_argon2
    assert long_secret
    leaked = PASSWORD in await stored_credentials_json(database)
    assert not leaked
    accepted = await auth.verify_session(token)
    assert accepted


async def test_each_setup_generates_its_own_session_secret(
    auth: AuthService, settings: SettingsService, tmp_path: Path
) -> None:
    other_path = tmp_path / "other.db"
    upgrade_to_head(other_path)
    other_db = create_database(other_path)
    try:
        other_settings = SettingsService(other_db.session_factory)
        await auth.setup(USERNAME, PASSWORD)
        await AuthService(other_settings).setup(USERNAME, PASSWORD)

        first = await settings.get(CREDENTIALS)
        second = await other_settings.get(CREDENTIALS)
    finally:
        await other_db.dispose()

    assert first is not None
    assert second is not None
    differ = first.session_secret != second.session_secret
    assert differ


async def test_second_setup_raises_and_keeps_the_first_credentials(
    auth: AuthService, settings: SettingsService
) -> None:
    await auth.setup(USERNAME, PASSWORD)
    first = await settings.get(CREDENTIALS)

    with pytest.raises(SetupAlreadyDone):
        await auth.setup("intruder", "another password")

    unchanged = await settings.get(CREDENTIALS) == first
    assert unchanged


async def test_concurrent_setups_leave_one_winner(
    auth: AuthService, settings: SettingsService
) -> None:
    results = await asyncio.gather(
        auth.setup("first", "first password"),
        auth.setup("second", "second password"),
        return_exceptions=True,
    )

    winners = [r for r in results if isinstance(r, str)]
    loser_count = sum(isinstance(r, SetupAlreadyDone) for r in results)
    # Counted apart from the list, so a failure cannot print the session tokens.
    winner_count = len(winners)
    assert winner_count == 1
    assert loser_count == 1
    credentials = await settings.get(CREDENTIALS)
    assert credentials is not None
    assert credentials.username in {"first", "second"}
    accepted = await auth.verify_session(winners[0])
    assert accepted


@pytest.mark.parametrize("set_up_first", [True, False], ids=["after-setup", "before-setup"])
async def test_concurrent_logins_hash_at_most_two_at_a_time(
    auth: AuthService, peak_argon2_calls: Callable[[], int], set_up_first: bool
) -> None:
    if set_up_first:
        await auth.setup(USERNAME, PASSWORD)

    await asyncio.gather(*(auth.login(USERNAME, "not the password") for _ in range(6)))

    assert peak_argon2_calls() == 2


async def test_setup_shares_the_hashing_cap_with_logins(
    auth: AuthService, peak_argon2_calls: Callable[[], int]
) -> None:
    await asyncio.gather(
        auth.setup(USERNAME, PASSWORD),
        *(auth.login(USERNAME, "not the password") for _ in range(4)),
    )

    assert peak_argon2_calls() == 2


async def test_login_returns_a_valid_session_for_the_right_pair(
    auth: AuthService, seeded: Credentials
) -> None:
    token = await auth.login(USERNAME, PASSWORD)

    assert token is not None
    accepted = await auth.verify_session(token)
    assert accepted


async def test_login_with_a_wrong_password_returns_none_and_still_hashes(
    auth: AuthService, seeded: Credentials, verify_calls: list[str]
) -> None:
    rejected = await auth.login(USERNAME, "not the password") is None
    assert rejected
    assert len(verify_calls) == 1


async def test_login_with_a_wrong_username_returns_none_and_still_hashes(
    auth: AuthService, seeded: Credentials, verify_calls: list[str]
) -> None:
    rejected = await auth.login("someone-else", PASSWORD) is None
    assert rejected
    assert len(verify_calls) == 1


async def test_login_with_a_non_ascii_username_returns_none(
    auth: AuthService, seeded: Credentials
) -> None:
    rejected = await auth.login("lecteuré", PASSWORD) is None
    assert rejected


async def test_login_before_setup_returns_none_and_still_hashes(
    auth: AuthService, verify_calls: list[str]
) -> None:
    rejected = await auth.login(USERNAME, PASSWORD) is None
    assert rejected
    assert len(verify_calls) == 1


async def test_login_before_setup_stays_none_for_the_dummy_source_password(
    auth: AuthService,
) -> None:
    rejected = await auth.login(USERNAME, DUMMY_SOURCE_PASSWORD) is None
    assert rejected
    rejected = await auth.login("", DUMMY_SOURCE_PASSWORD) is None
    assert rejected


async def test_verify_session_rejects_a_token_after_the_password_hash_changes(
    auth: AuthService, settings: SettingsService, seeded: Credentials
) -> None:
    token = await auth.login(USERNAME, PASSWORD)
    assert token is not None

    await settings.set(
        CREDENTIALS, seeded.model_copy(update={"password_hash": hash_password("new password")})
    )

    rejected = await auth.verify_session(token) is False
    assert rejected


async def test_verify_session_rejects_a_token_after_the_username_changes(
    auth: AuthService, settings: SettingsService, seeded: Credentials
) -> None:
    token = await auth.login(USERNAME, PASSWORD)
    assert token is not None

    await settings.set(CREDENTIALS, seeded.model_copy(update={"username": "someone-else"}))

    rejected = await auth.verify_session(token) is False
    assert rejected


async def test_verify_session_rejects_a_token_signed_with_another_secret(
    auth: AuthService, seeded: Credentials
) -> None:
    fingerprint = session_fingerprint("another-secret", USERNAME, seeded.password_hash)
    forged = SessionSigner("another-secret").issue(fingerprint)

    rejected = await auth.verify_session(forged) is False
    assert rejected


async def test_verify_session_rejects_a_fingerprint_for_another_username(
    auth: AuthService, seeded: Credentials
) -> None:
    fingerprint = session_fingerprint(seeded.session_secret, "someone-else", seeded.password_hash)
    other = SessionSigner(seeded.session_secret).issue(fingerprint)

    rejected = await auth.verify_session(other) is False
    assert rejected


async def test_verify_session_accepts_the_fingerprint_of_the_stored_credentials(
    auth: AuthService, seeded: Credentials
) -> None:
    fingerprint = session_fingerprint(seeded.session_secret, USERNAME, seeded.password_hash)
    token = SessionSigner(seeded.session_secret).issue(fingerprint)

    accepted = await auth.verify_session(token)
    assert accepted


async def test_verify_session_rejects_a_token_past_its_max_age(
    auth: AuthService, seeded: Credentials, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = await auth.login(USERNAME, PASSWORD)
    assert token is not None

    monkeypatch.setattr(auth_module, "SESSION_MAX_AGE_SECONDS", -1)

    rejected = await auth.verify_session(token) is False
    assert rejected


async def test_verify_session_rejects_when_no_credentials_exist(auth: AuthService) -> None:
    token = SessionSigner("any-secret").issue("any-fingerprint")

    rejected = await auth.verify_session(token) is False
    assert rejected


async def test_verify_session_rejects_garbage(auth: AuthService, seeded: Credentials) -> None:
    rejected = await auth.verify_session("not-a-token") is False
    assert rejected


async def test_local_bypass_is_off_by_default(auth: AuthService) -> None:
    assert await auth.local_bypass_enabled() is False


async def test_local_bypass_is_on_after_the_setting_is_written(
    auth: AuthService, settings: SettingsService
) -> None:
    await settings.set(LOCAL_BYPASS, True)

    assert await auth.local_bypass_enabled() is True


def test_credentials_are_frozen() -> None:
    credentials = Credentials(username="u", password_hash="h", session_secret="s")

    with pytest.raises(ValidationError):
        credentials.username = "other"


def test_credentials_repr_hides_the_hash_and_the_secret() -> None:
    shown = repr(
        Credentials(username="u", password_hash="hash-value", session_secret="secret-value")
    )

    assert "hash-value" not in shown
    assert "secret-value" not in shown
