import logging
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

from tomarr.app import create_app, lifespan
from tomarr.core.database import Database


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

    assert revision == "0002"
    assert "setting" in tables


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
        assert pool.checkedin() == 1

    assert pool.checkedin() == 0
    assert database.engine.pool is not pool


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
