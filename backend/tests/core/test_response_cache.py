import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import select

from tomarr.core.database import Database, create_database
from tomarr.core.migrations import upgrade_to_head
from tomarr.core.response_cache import CachedResponse, ResponseCache
from tomarr.domain.http_cache import HttpCacheEntry

URL = "https://api.example.test/series?key=hunter2"


class Clock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.time = start

    def __call__(self) -> float:
        return self.time


@pytest.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    path = tmp_path / "tomarr.db"
    upgrade_to_head(path)
    db = create_database(path)
    yield db
    await db.dispose()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def cache(database: Database, clock: Clock) -> ResponseCache:
    return ResponseCache(database.session_factory, clock)


def _response(body: bytes = b'{"ok": true}') -> CachedResponse:
    return CachedResponse(
        status_code=200, headers=[("content-type", "application/json")], body=body
    )


async def _rows(database: Database) -> list[HttpCacheEntry]:
    async with database.session_factory() as session:
        return list((await session.scalars(select(HttpCacheEntry))).all())


async def test_get_returns_none_on_a_miss(cache: ResponseCache) -> None:
    assert await cache.get("mangabaka", "GET", URL) is None


async def test_get_returns_what_put_stored(cache: ResponseCache) -> None:
    stored = CachedResponse(
        status_code=200,
        headers=[("set-cookie", "a=1"), ("set-cookie", "b=2"), ("content-encoding", "gzip")],
        body=b"\x1f\x8b\x00raw bytes",
    )

    await cache.put("mangabaka", "GET", URL, stored, ttl=60)

    assert await cache.get("mangabaka", "GET", URL) == stored


async def test_get_returns_none_once_the_entry_has_expired(
    cache: ResponseCache, clock: Clock
) -> None:
    await cache.put("mangabaka", "GET", URL, _response(), ttl=60)

    clock.time += 59
    assert await cache.get("mangabaka", "GET", URL) is not None
    clock.time += 1
    assert await cache.get("mangabaka", "GET", URL) is None


async def test_put_on_an_existing_key_replaces_the_row(
    cache: ResponseCache, database: Database, clock: Clock
) -> None:
    await cache.put("mangabaka", "GET", URL, _response(b"old"), ttl=60)
    clock.time += 10

    await cache.put("mangabaka", "GET", URL, _response(b"new"), ttl=60)

    rows = await _rows(database)
    assert len(rows) == 1
    assert rows[0].expires_at == 1_070.0
    replayed = await cache.get("mangabaka", "GET", URL)
    assert replayed is not None
    assert replayed.body == b"new"


async def test_the_same_url_under_two_adapters_has_two_keys(
    cache: ResponseCache, database: Database
) -> None:
    await cache.put("mangabaka", "GET", URL, _response(b"one"), ttl=60)
    await cache.put("rakuten", "GET", URL, _response(b"two"), ttl=60)

    assert len({row.key for row in await _rows(database)}) == 2
    first = await cache.get("mangabaka", "GET", URL)
    second = await cache.get("rakuten", "GET", URL)
    assert first is not None
    assert second is not None
    assert (first.body, second.body) == (b"one", b"two")


async def test_the_key_is_a_sha256_digest_and_no_column_holds_the_url(
    cache: ResponseCache, database: Database
) -> None:
    await cache.put("mangabaka", "GET", URL, _response(), ttl=60)

    [row] = await _rows(database)
    assert re.fullmatch(r"[0-9a-f]{64}", row.key)
    stored = [row.key, row.adapter, row.status_code, row.headers, row.body, row.expires_at]
    assert "hunter2" not in repr(stored)
    assert "api.example.test" not in repr(stored)
