from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import QueuePool

from tomarr.core.database import Database, create_database


@pytest.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    db = create_database(tmp_path / "tomarr.db")
    yield db
    await db.dispose()


async def test_pragmas_apply_to_every_connection(database: Database) -> None:
    async with database.engine.connect() as first, database.engine.connect() as second:
        first_raw = await first.get_raw_connection()
        second_raw = await second.get_raw_connection()
        assert first_raw.driver_connection is not second_raw.driver_connection

        for connection in (first, second):
            journal_mode = (await connection.execute(text("PRAGMA journal_mode"))).scalar_one()
            foreign_keys = (await connection.execute(text("PRAGMA foreign_keys"))).scalar_one()
            assert journal_mode == "wal"
            assert foreign_keys == 1


async def test_foreign_key_violation_is_rejected(database: Database) -> None:
    async with database.engine.begin() as connection:
        await connection.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
        await connection.execute(
            text("CREATE TABLE child (parent_id INTEGER REFERENCES parent (id))")
        )

    with pytest.raises(IntegrityError):
        async with database.engine.begin() as connection:
            await connection.execute(text("INSERT INTO child (parent_id) VALUES (1)"))


async def test_dispose_closes_pooled_connections(database: Database) -> None:
    pool = database.engine.pool
    assert isinstance(pool, QueuePool)
    async with database.engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    assert pool.checkedin() == 1

    await database.dispose()

    assert pool.checkedin() == 0
    assert database.engine.pool is not pool
