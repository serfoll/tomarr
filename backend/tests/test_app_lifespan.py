import asyncio
import json
import logging
import sqlite3
import time
from contextlib import AsyncExitStack
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.pool import QueuePool

from tests.helpers.event_stream import EventStream
from tomarr.app import create_app, lifespan
from tomarr.commands.purge_http_cache import PURGE_HTTP_CACHE
from tomarr.commands.runner import CommandRunner
from tomarr.commands.scheduler import CommandScheduler
from tomarr.core.broadcaster import Broadcaster
from tomarr.core.database import Database
from tomarr.core.http import HttpClientFactory
from tomarr.domain.command import Command, CommandStatus
from tomarr.services.auth import CREDENTIALS, Credentials
from tomarr.services.commands import CommandService
from tomarr.services.settings import SettingsService

# The runner and scheduler use the real clock here, so a test polls for the outcome it waits on.
POLL_TIMEOUT = 5.0
POLL_INTERVAL = 0.01


def test_lifespan_creates_config_and_log_file_and_releases_handlers(tmp_path: Path) -> None:
    root = logging.getLogger()
    handlers_before = list(root.handlers)

    with TestClient(create_app()) as client:
        assert (tmp_path / "config.toml").is_file()
        assert (tmp_path / "logs" / "tomarr.log").is_file()
        assert len(root.handlers) == len(handlers_before) + 2
        assert client.get("/api/v1/system/health").status_code == 200

    assert root.handlers == handlers_before


def test_lifespan_applies_log_level_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOMARR__LOG__LEVEL", "debug")

    with TestClient(create_app()):
        assert logging.getLogger().level == logging.DEBUG


def test_lifespan_redacts_the_generated_api_key(tmp_path: Path) -> None:
    with TestClient(create_app()):
        config = (tmp_path / "config.toml").read_text(encoding="utf-8")
        apikey = next(
            line.split("=", 1)[1].strip().strip('"')
            for line in config.splitlines()
            if line.startswith("apikey")
        )
        logging.getLogger("tomarr.test").info("calling with %s", apikey)

    log = (tmp_path / "logs" / "tomarr.log").read_text(encoding="utf-8")
    leaked = apikey in log
    assert not leaked


def test_lifespan_migrates_the_database_to_head(tmp_path: Path) -> None:
    path = tmp_path / "tomarr.db"
    assert not path.exists()

    with TestClient(create_app()):
        engine = create_engine(f"sqlite:///{path}")
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            tables = connection.execute(text("SELECT name FROM sqlite_master")).scalars().all()
        engine.dispose()

    assert revision == "0003"
    assert "setting" in tables
    assert "http_cache" in tables


def test_lifespan_opens_the_database_and_disposes_it_on_shutdown() -> None:
    app = create_app()

    with TestClient(app) as client:
        database = app.state.database
        assert isinstance(database, Database)
        pool = database.engine.pool
        assert isinstance(pool, QueuePool)

        async def open_connection() -> None:
            async with database.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))

        assert client.portal is not None
        client.portal.call(open_connection)
        # The command workers and scheduler use the pool too, so it can hold more than one.
        assert pool.checkedin() >= 1

    assert pool.checkedin() == 0
    assert database.engine.pool is not pool


def test_lifespan_puts_the_http_client_factory_on_app_state() -> None:
    app = create_app()

    with TestClient(app):
        assert isinstance(app.state.http, HttpClientFactory)


def test_lifespan_turns_on_wal_before_the_first_request(tmp_path: Path) -> None:
    with TestClient(create_app()):
        connection = sqlite3.connect(tmp_path / "tomarr.db")
        try:
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            connection.close()

    assert journal_mode == "wal"


def test_lifespan_logs_a_failed_migration_fails_startup_and_releases_logging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_migration(_path: Path) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("tomarr.app.upgrade_to_head", broken_migration)
    root = logging.getLogger()
    handlers_before = list(root.handlers)

    with pytest.raises(RuntimeError, match="boom"), TestClient(create_app()):
        pytest.fail("startup should not complete")

    assert root.handlers == handlers_before
    log = (tmp_path / "logs" / "tomarr.log").read_text(encoding="utf-8")
    assert "Database startup failed" in log
    assert "boom" in log


async def test_lifespan_releases_logging_when_dispose_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def broken_dispose(_self: Database) -> None:
        raise RuntimeError("dispose failed")

    monkeypatch.setattr(Database, "dispose", broken_dispose)
    app = create_app()
    root = logging.getLogger()
    handlers_before = list(root.handlers)

    with pytest.raises(RuntimeError, match="dispose failed"):
        async with lifespan(app):
            pass

    assert root.handlers == handlers_before


async def test_lifespan_disposes_database_and_releases_logging_when_the_body_raises() -> None:
    app = create_app()
    root = logging.getLogger()
    handlers_before = list(root.handlers)

    started: list[tuple[Database, object]] = []

    with pytest.raises(RuntimeError, match="boom"):
        async with lifespan(app):
            started.append((app.state.database, app.state.database.engine.pool))
            raise RuntimeError("boom")

    [(database, pool)] = started
    assert database.engine.pool is not pool
    assert root.handlers == handlers_before


NO_CREDENTIALS_WARNING = "No credentials are set"


def test_lifespan_warns_while_no_credentials_are_set(tmp_path: Path) -> None:
    with TestClient(create_app()):
        pass

    log = (tmp_path / "logs" / "tomarr.log").read_text(encoding="utf-8")
    assert NO_CREDENTIALS_WARNING in log
    assert '"level": "WARNING"' in log


def test_lifespan_does_not_warn_once_credentials_are_set(tmp_path: Path) -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/auth/setup", data={"username": "reader", "password": "correct horse"}
        )
        assert response.status_code == 204
    log_file = tmp_path / "logs" / "tomarr.log"
    log_file.unlink()

    with TestClient(create_app()):
        pass

    assert NO_CREDENTIALS_WARNING not in log_file.read_text(encoding="utf-8")


RESET_PASSWORD_ENV = "TOMARR__AUTH__RESET_PASSWORD"
RESET_PASSWORD = "a brand new password"


def warnings_in_log(tmp_path: Path) -> list[str]:
    lines = (tmp_path / "logs" / "tomarr.log").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    return [record["message"] for record in records if record["level"] == "WARNING"]


def set_up_once(username: str = "reader", password: str = "correct horse") -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/auth/setup", data={"username": username, "password": password}
        )
        assert response.status_code == 204


def test_lifespan_warns_once_naming_the_variable_while_the_reset_window_is_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_up_once()
    (tmp_path / "logs" / "tomarr.log").unlink()
    monkeypatch.setenv(RESET_PASSWORD_ENV, "true")

    with TestClient(create_app()):
        pass

    warnings = warnings_in_log(tmp_path)
    assert [w for w in warnings if RESET_PASSWORD_ENV in w] == [
        f"{RESET_PASSWORD_ENV} is set, so the sign-up page is open to replace the login. "
        "Sign up again, then remove the variable and restart Tomarr."
    ]
    assert not any(NO_CREDENTIALS_WARNING in w for w in warnings)


def test_lifespan_warns_once_that_the_variable_is_still_set_after_the_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_up_once()
    monkeypatch.setenv(RESET_PASSWORD_ENV, "true")
    set_up_once("owner", RESET_PASSWORD)
    (tmp_path / "logs" / "tomarr.log").unlink()

    with TestClient(create_app()):
        pass

    warnings = warnings_in_log(tmp_path)
    assert [w for w in warnings if RESET_PASSWORD_ENV in w] == [
        f"{RESET_PASSWORD_ENV} is still set, but the password was already reset. "
        "Remove the variable and restart Tomarr."
    ]
    assert not any(NO_CREDENTIALS_WARNING in w for w in warnings)


def test_lifespan_does_not_name_the_variable_while_it_is_unset(tmp_path: Path) -> None:
    with TestClient(create_app()):
        pass

    warnings = warnings_in_log(tmp_path)
    assert not any(RESET_PASSWORD_ENV in w for w in warnings)
    assert any(NO_CREDENTIALS_WARNING in w for w in warnings)


def test_a_reset_logs_neither_the_password_nor_the_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    set_up_once()
    monkeypatch.setenv(RESET_PASSWORD_ENV, "true")
    app = create_app()

    async def stored_hash() -> str:
        credentials = await SettingsService(app.state.database.session_factory).get(CREDENTIALS)
        assert credentials is not None
        return credentials.password_hash

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/setup", data={"username": "owner", "password": RESET_PASSWORD}
        )
        assert response.status_code == 204
        assert client.portal is not None
        password_hash = client.portal.call(stored_hash)
    with TestClient(create_app()):
        pass

    logged = [record.getMessage() for record in caplog.records]
    logged.append((tmp_path / "logs" / "tomarr.log").read_text(encoding="utf-8"))
    # Counted, so a failure cannot print the password or the hash.
    leaks = sum(RESET_PASSWORD in text or password_hash in text for text in logged)
    assert leaks == 0


def test_debug_logging_of_a_setup_and_login_leaks_no_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("TOMARR__LOG__LEVEL", "debug")
    app = create_app()
    form = {"username": "owner", "password": RESET_PASSWORD}

    async def stored_credentials() -> Credentials:
        credentials = await SettingsService(app.state.database.session_factory).get(CREDENTIALS)
        assert credentials is not None
        return credentials

    with TestClient(app) as client:
        assert client.post("/api/v1/auth/setup", data=form).status_code == 204
        assert client.post("/api/v1/auth/login", data=form).status_code == 204
        assert client.portal is not None
        credentials = client.portal.call(stored_credentials)

    logged = [record.getMessage() for record in caplog.records]
    logged.append((tmp_path / "logs" / "tomarr.log").read_text(encoding="utf-8"))
    leaked = (RESET_PASSWORD, credentials.password_hash, credentials.session_secret)
    # Counted, so a failure cannot print a credential.
    leaks = [sum(value in text for text in logged) for value in leaked]
    assert leaks == [0, 0, 0]


def test_lifespan_puts_the_command_queue_on_app_state() -> None:
    app = create_app()

    with TestClient(app):
        assert isinstance(app.state.commands, CommandService)
        assert isinstance(app.state.broadcaster, Broadcaster)
        assert isinstance(app.state.runner, CommandRunner)
        assert isinstance(app.state.scheduler, CommandScheduler)


async def purge_commands(app: FastAPI) -> list[Command]:
    database: Database = app.state.database
    async with database.session_factory() as session:
        commands = await session.scalars(
            select(Command).where(Command.type == PURGE_HTTP_CACHE).order_by(Command.id)
        )
        return list(commands)


async def wait_for_completed_purge(app: FastAPI) -> list[Command]:
    async with asyncio.timeout(POLL_TIMEOUT):
        while True:
            commands = await purge_commands(app)
            if any(command.status is CommandStatus.COMPLETED for command in commands):
                return commands
            await asyncio.sleep(POLL_INTERVAL)


async def test_the_first_start_queues_a_purge_that_completes() -> None:
    app = create_app()

    async with lifespan(app):
        [command] = await wait_for_completed_purge(app)

    assert command.status is CommandStatus.COMPLETED
    assert command.result == {"deleted": 0}


async def test_a_command_left_running_is_requeued_at_start_and_runs(database: Database) -> None:
    now = time.time()
    interrupted = Command(
        type=PURGE_HTTP_CACHE,
        payload={},
        status=CommandStatus.RUNNING,
        priority=0,
        queued_at=now,
        started_at=now,
    )
    async with database.session_factory.begin() as session:
        session.add(interrupted)
    app = create_app()

    async with lifespan(app):
        [command] = await wait_for_completed_purge(app)

    assert command.id == interrupted.id
    assert command.result == {"deleted": 0}


async def test_shutdown_stops_every_task_and_ends_an_open_event_stream(api_key: str) -> None:
    app = create_app()
    before = asyncio.all_tasks()

    async with AsyncExitStack() as running:
        await running.enter_async_context(lifespan(app))
        async with EventStream(app, api_key) as stream:
            await stream.next_event()

            await running.aclose()
            await stream.ended()

    assert stream.status == 200
    assert asyncio.all_tasks() <= before


async def test_shutdown_closes_the_broadcaster_before_stopping_the_scheduler(
    api_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app()
    stop = CommandScheduler.stop
    subscribers_at_stop: list[int] = []

    async def recording_stop(scheduler: CommandScheduler) -> None:
        subscribers_at_stop.append(app.state.broadcaster.subscriber_count)
        await stop(scheduler)

    monkeypatch.setattr(CommandScheduler, "stop", recording_stop)

    async with AsyncExitStack() as running:
        await running.enter_async_context(lifespan(app))
        async with EventStream(app, api_key) as stream:
            await stream.next_event()
            assert app.state.broadcaster.subscriber_count == 1

            await running.aclose()

    assert subscribers_at_stop == [0]
