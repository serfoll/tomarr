import logging
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.operations import MigrationScript
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from tomarr.core.database import create_database
from tomarr.core.migrations import SCRIPT_LOCATION, upgrade_to_head
from tomarr.domain.base import Base
from tomarr.domain.command import Command
from tomarr.domain.http_cache import HttpCacheEntry
from tomarr.domain.setting import Setting


def _config(path: Path) -> Config:
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return config


def _head_revision() -> str | None:
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)
    return ScriptDirectory.from_config(config).get_current_head()


def _current_revision(path: Path) -> str | None:
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()
    engine.dispose()
    return revision


def _settings(path: Path) -> list[tuple[str, str]]:
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT key, value FROM setting ORDER BY key")).all()
    engine.dispose()
    return [(row.key, row.value) for row in rows]


def test_upgrade_creates_database_at_head(tmp_path: Path) -> None:
    path = tmp_path / "tomarr.db"

    upgrade_to_head(path)

    assert path.is_file()
    engine = create_engine(f"sqlite:///{path}")
    assert "setting" in inspect(engine).get_table_names()
    engine.dispose()
    head = _head_revision()
    assert head is not None
    assert _current_revision(path) == head


def test_second_upgrade_changes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "tomarr.db"
    upgrade_to_head(path)
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO setting (key, value) VALUES ('kept', '"yes"')"""))
    engine.dispose()
    revision = _current_revision(path)

    upgrade_to_head(path)

    assert _current_revision(path) == revision
    assert _settings(path) == [("kept", '"yes"')]


def test_migrated_schema_matches_models(tmp_path: Path) -> None:
    path = tmp_path / "tomarr.db"
    upgrade_to_head(path)
    assert Setting.__tablename__ in Base.metadata.tables
    assert HttpCacheEntry.__tablename__ in Base.metadata.tables
    assert Command.__tablename__ in Base.metadata.tables

    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()

    assert differences == []


def test_upgrade_creates_the_command_table_and_the_indexes(tmp_path: Path) -> None:
    path = tmp_path / "tomarr.db"

    upgrade_to_head(path)

    engine = create_engine(f"sqlite:///{path}")
    inspector = inspect(engine)
    command_indexes = {
        index["name"]: index["column_names"] for index in inspector.get_indexes("command")
    }
    cache_indexes = {
        index["name"]: index["column_names"] for index in inspector.get_indexes("http_cache")
    }
    engine.dispose()
    assert command_indexes == {"ix_command_claim": ["status", "priority", "queued_at"]}
    assert cache_indexes == {"ix_http_cache_expires_at": ["expires_at"]}


def test_upgrade_finds_scripts_from_any_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    path = tmp_path / "tomarr.db"

    upgrade_to_head(path)

    assert _current_revision(path) == _head_revision()


def test_upgrade_leaves_logging_handlers_alone(tmp_path: Path) -> None:
    root = logging.getLogger()
    handler = logging.NullHandler()
    root.addHandler(handler)
    try:
        before = list(root.handlers)

        upgrade_to_head(tmp_path / "tomarr.db")

        # Handlers have no __eq__, so list equality compares them by identity.
        assert root.handlers == before
    finally:
        root.removeHandler(handler)


def test_autogenerate_runs_in_batch_mode(tmp_path: Path) -> None:
    path = tmp_path / "tomarr.db"
    upgrade_to_head(path)
    options: dict[str, object] = {}

    def capture(
        context: MigrationContext, _revision: object, scripts: list[MigrationScript]
    ) -> None:
        options.update(context.opts)
        scripts.clear()

    command.revision(_config(path), autogenerate=True, process_revision_directives=capture)

    assert options["render_as_batch"] is True


@pytest.mark.parametrize("name", ["a?b", "a%b", "a#b", "a b", "設定ä"])
async def test_odd_characters_in_the_config_path(tmp_path: Path, name: str) -> None:
    folder = tmp_path / name
    folder.mkdir()
    path = folder / "tomarr.db"

    upgrade_to_head(path)
    database = create_database(path)
    try:
        async with database.engine.connect() as connection:
            await connection.execute(text("SELECT count(*) FROM setting"))
    finally:
        await database.dispose()

    assert _entries(tmp_path) == [name]
    assert "setting" in _tables(path)


def _entries(folder: Path) -> list[str]:
    return sorted(entry.name for entry in folder.iterdir())


def _tables(path: Path) -> list[str]:
    # The standard library driver takes the path as is, with no URL parsing in between.
    connection = sqlite3.connect(path)
    try:
        return [row[0] for row in connection.execute("SELECT name FROM sqlite_master")]
    finally:
        connection.close()
