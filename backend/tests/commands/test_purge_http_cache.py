import pytest
from pydantic import ValidationError

from tests.helpers.clock import FakeClock
from tomarr.commands.purge_http_cache import PURGE_HTTP_CACHE_INTERVAL, make_purge_handler
from tomarr.core.database import Database
from tomarr.core.response_cache import CachedResponse, ResponseCache
from tomarr.services.settings import registry


@pytest.fixture
def clock() -> FakeClock:
    clock = FakeClock()
    clock.now = 1_000.0
    return clock


@pytest.fixture
def cache(database: Database, clock: FakeClock) -> ResponseCache:
    return ResponseCache(database.session_factory, clock)


async def test_the_handler_reports_how_many_rows_it_deleted(
    cache: ResponseCache, clock: FakeClock
) -> None:
    response = CachedResponse(status_code=200, headers=[], body=b"{}")
    await cache.put("mangabaka", "GET", "https://api.example.test/a", response, ttl=10)
    await cache.put("mangabaka", "GET", "https://api.example.test/b", response, ttl=10)
    await cache.put("mangabaka", "GET", "https://api.example.test/c", response, ttl=100)
    clock.now += 10
    handler = make_purge_handler(cache)

    assert await handler({}) == {"deleted": 2}
    assert await handler({}) == {"deleted": 0}


def test_the_interval_is_a_declared_setting_that_defaults_to_a_day() -> None:
    declared = registry.keys()

    assert PURGE_HTTP_CACHE_INTERVAL in declared
    assert PURGE_HTTP_CACHE_INTERVAL.name == "schedule.purge_http_cache"
    assert PURGE_HTTP_CACHE_INTERVAL.default == 86_400


def test_the_interval_rejects_a_negative_value() -> None:
    adapter = PURGE_HTTP_CACHE_INTERVAL.adapter

    assert adapter.validate_python(0) == 0
    with pytest.raises(ValidationError):
        adapter.validate_python(-1)
