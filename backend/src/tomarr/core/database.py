from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import URL, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import ConnectionPoolEntry, PoolProxiedConnection


@dataclass(frozen=True)
class Database:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    async def dispose(self) -> None:
        await self.engine.dispose()


def create_database(path: Path) -> Database:
    engine = create_async_engine(URL.create("sqlite+aiosqlite", database=str(path)))
    event.listen(engine.sync_engine, "connect", _set_pragmas)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return Database(engine=engine, session_factory=session_factory)


def _set_pragmas(dbapi_connection: PoolProxiedConnection, _record: ConnectionPoolEntry) -> None:
    # Foreign keys is per connection, and journal_mode cannot change inside a transaction. The
    # sqlite3 driver opens no transaction before a PRAGMA in its default (legacy) mode, so both
    # run cleanly here. The autocommit=False connect arg would break that, so it is not set.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
