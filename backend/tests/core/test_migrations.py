import logging
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.operations import MigrationScript
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from tests.helpers.migrations import head_revision
from tomarr.core.database import create_database
from tomarr.core.migrations import SCRIPT_LOCATION, upgrade_to_head
from tomarr.domain.alias import Alias
from tomarr.domain.base import Base
from tomarr.domain.chapter import Chapter, Episode
from tomarr.domain.command import Command
from tomarr.domain.edition import Edition
from tomarr.domain.external_id import SeriesExternalId, VolumeExternalId
from tomarr.domain.http_cache import HttpCacheEntry
from tomarr.domain.mapping import Mapping
from tomarr.domain.series import Series
from tomarr.domain.setting import Setting
from tomarr.domain.volume import Volume

LIBRARY_MODELS = [
    Series,
    Edition,
    Volume,
    Chapter,
    Episode,
    Mapping,
    SeriesExternalId,
    VolumeExternalId,
    Alias,
]


def _config(path: Path) -> Config:
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return config


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
    head = head_revision()
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
    for model in LIBRARY_MODELS:
        assert model.__tablename__ in Base.metadata.tables

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


def _index_columns(path: Path, table: str) -> dict[str, list[str | None]]:
    engine = create_engine(f"sqlite:///{path}")
    indexes = inspect(engine).get_indexes(table)
    engine.dispose()
    return {index["name"]: index["column_names"] for index in indexes if index["name"]}


# Reflecting `episode` warns that it cannot read the expression index, which is expected.
@pytest.mark.filterwarnings("ignore:Skipped unsupported reflection of expression-based index")
def test_upgrade_creates_the_indexes_the_library_reads_and_cascades_use(tmp_path: Path) -> None:
    path = tmp_path / "tomarr.db"

    upgrade_to_head(path)

    mapping = _index_columns(path, "mapping")
    assert mapping["ix_mapping_volume_id"] == ["volume_id"]
    assert mapping["ix_mapping_chapter_id"] == ["chapter_id"]
    assert _index_columns(path, "episode")["ix_episode_chapter_id"] == ["chapter_id"]


def test_upgrade_creates_the_external_id_lookup_indexes(tmp_path: Path) -> None:
    path = tmp_path / "tomarr.db"

    upgrade_to_head(path)

    assert _index_columns(path, "series_external_id")["ix_series_external_id_provider_value"] == [
        "provider",
        "value",
    ]
    assert _index_columns(path, "volume_external_id")["ix_volume_external_id_provider_value"] == [
        "provider",
        "value",
    ]


def _table_names(path: Path) -> set[str]:
    engine = create_engine(f"sqlite:///{path}")
    names = set(inspect(engine).get_table_names())
    engine.dispose()
    return names


def test_upgrade_creates_the_library_tables(tmp_path: Path) -> None:
    path = tmp_path / "tomarr.db"

    upgrade_to_head(path)

    assert {model.__tablename__ for model in LIBRARY_MODELS} <= _table_names(path)


def test_downgrade_to_0003_removes_the_library_tables(tmp_path: Path) -> None:
    path = tmp_path / "tomarr.db"
    upgrade_to_head(path)

    command.downgrade(_config(path), "0003")

    assert _current_revision(path) == "0003"
    assert _table_names(path) == {"alembic_version", "setting", "http_cache", "command"}


def test_upgrade_finds_scripts_from_any_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    path = tmp_path / "tomarr.db"

    upgrade_to_head(path)

    assert _current_revision(path) == head_revision()


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
