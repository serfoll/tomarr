import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

from tomarr.app import create_app, lifespan
from tomarr.core.database import Database
from tomarr.core.logging import close_logging

UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in [name for name in os.environ if name.startswith("TOMARR__")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("TOMARR_CONFIG_DIR", str(tmp_path))
    root = logging.getLogger()
    root_level = root.level
    saved = {
        name: (lg.level, lg.propagate, list(lg.handlers))
        for name in UVICORN_LOGGERS
        for lg in [logging.getLogger(name)]
    }
    yield
    close_logging()
    root.setLevel(root_level)
    for name, (level, propagate, handlers) in saved.items():
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.propagate = propagate
        lg.handlers[:] = handlers


def test_lifespan_creates_config_and_log_file_and_releases_handlers(tmp_path: Path) -> None:
    root = logging.getLogger()
    handlers_before = list(root.handlers)

    with TestClient(create_app()) as client:
        assert (tmp_path / "config.toml").is_file()
        assert (tmp_path / "logs" / "tomarr.log").is_file()
        assert len(root.handlers) == len(handlers_before) + 2
        assert client.get("/api/v1/system/status").status_code == 200

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

    assert apikey not in (tmp_path / "logs" / "tomarr.log").read_text(encoding="utf-8")


def test_lifespan_migrates_the_database_to_head(tmp_path: Path) -> None:
    path = tmp_path / "tomarr.db"
    assert not path.exists()

    with TestClient(create_app()):
        engine = create_engine(f"sqlite:///{path}")
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            tables = connection.execute(text("SELECT name FROM sqlite_master")).scalars().all()
        engine.dispose()

    assert revision == "0001"
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


def test_lifespan_fails_startup_and_releases_logging_when_migration_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_migration(_path: Path) -> None:
        raise RuntimeError("migration failed")

    monkeypatch.setattr("tomarr.app.upgrade_to_head", broken_migration)
    root = logging.getLogger()
    handlers_before = list(root.handlers)

    with pytest.raises(RuntimeError, match="migration failed"), TestClient(create_app()):
        pytest.fail("startup should not complete")

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
