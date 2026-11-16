from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import httpx2
import pytest

from tests.helpers.cassettes import recorded_response_body
from tests.helpers.clock import FakeClock
from tests.helpers.http import make_factory
from tomarr.core.database import Database
from tomarr.core.errors import ProviderError, RateLimited
from tomarr.domain.external_id import Provider
from tomarr.domain.series import Format
from tomarr.providers.base import SeriesLookup, SeriesSearch
from tomarr.providers.mangabaka.client import MangaBakaClient

RECORDED_SERIES = (
    Path(__file__).parents[2]
    / "fixtures"
    / "cassettes"
    / "providers"
    / "mangabaka"
    / "test_client"
    / "test_get_series_returns_the_series_by_its_id.yaml"
)
FRIEREN_IDS = {Provider.ANILIST: "118586", Provider.MANGAUPDATES: "ugf5dzu"}


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def wall() -> FakeClock:
    wall = FakeClock()
    wall.now = 1_700_000_000.0
    return wall


def stubbed_client(
    database: Database,
    clock: FakeClock,
    wall: FakeClock,
    respond: Callable[[httpx2.Request], httpx2.Response],
) -> MangaBakaClient:
    transport = httpx2.MockTransport(respond)
    return MangaBakaClient(make_factory(database, clock, wall, transport))


@pytest.mark.vcr
async def test_search_returns_candidates_with_external_ids(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    client = MangaBakaClient(make_factory(database, clock, wall))

    candidates = await client.search("frieren", limit=3)

    assert [candidate.provider_id for candidate in candidates] == ["1995", "100730", "64805"]
    frieren = candidates[0]
    assert frieren.provider is Provider.MANGABAKA
    assert frieren.title == "Frieren: Beyond Journey\u2019s End"
    assert frieren.format is Format.MANGA
    assert frieren.total_volumes == Decimal(15)
    assert frieren.external_ids == FRIEREN_IDS


@pytest.mark.vcr
async def test_get_series_returns_the_series_by_its_id(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    client = MangaBakaClient(make_factory(database, clock, wall))

    series = await client.get_series("1995")

    assert series.provider_id == "1995"
    assert series.title == "Frieren: Beyond Journey\u2019s End"
    assert series.external_ids == FRIEREN_IDS


def test_client_satisfies_both_provider_protocols(database: Database) -> None:
    client = MangaBakaClient(make_factory(database, FakeClock(), FakeClock()))

    # Assignments so pyright checks the method signatures. isinstance only checks the names.
    search: SeriesSearch = client
    lookup: SeriesLookup = client

    assert isinstance(search, SeriesSearch)
    assert isinstance(lookup, SeriesLookup)


async def test_a_429_raises_rate_limited_with_the_retry_after(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    client = stubbed_client(
        database, clock, wall, lambda _request: httpx2.Response(429, headers={"Retry-After": "10"})
    )

    with pytest.raises(RateLimited) as raised:
        await client.search("frieren")

    assert raised.value.service == "MangaBaka"
    assert raised.value.retry_after == 10


@pytest.mark.parametrize(
    ("response", "status"),
    [
        (httpx2.Response(500, json={"status": 500}), 500),
        (httpx2.Response(404, json={"status": 404}), 404),
        (httpx2.Response(200, json={"data": "not a list"}), 200),
        (httpx2.Response(200, content=b"<html>maintenance</html>"), 200),
    ],
)
async def test_an_unusable_response_raises_provider_error_without_the_url(
    database: Database, clock: FakeClock, wall: FakeClock, response: httpx2.Response, status: int
) -> None:
    client = stubbed_client(database, clock, wall, lambda _request: response)

    with pytest.raises(ProviderError) as search_error:
        await client.search("frieren")
    with pytest.raises(ProviderError) as series_error:
        await client.get_series("1995")

    for error in (search_error.value, series_error.value):
        assert error.provider == "MangaBaka"
        assert error.status == status
        assert "mangabaka.org" not in str(error)
        assert "frieren" not in str(error)


async def test_a_non_200_status_is_refused_even_when_the_body_has_the_right_shape(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    body = recorded_response_body(RECORDED_SERIES)
    client = stubbed_client(database, clock, wall, lambda _r: httpx2.Response(503, json=body))

    with pytest.raises(ProviderError) as raised:
        await client.get_series("1995")

    assert raised.value.status == 503


async def test_requests_go_to_the_v1_endpoints_with_the_query_and_limit(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(500)

    client = stubbed_client(database, clock, wall, respond)
    with pytest.raises(ProviderError):
        await client.search("blue box", limit=5)
    with pytest.raises(ProviderError):
        await client.get_series("1995")

    search_request, series_request = seen
    assert search_request.url.host == "api.mangabaka.org"
    assert search_request.url.path == "/v1/series/search"
    assert dict(search_request.url.params) == {"q": "blue box", "limit": "5"}
    assert series_request.url.path == "/v1/series/1995"
    assert "authorization" not in series_request.headers
    assert "x-api-key" not in series_request.headers


async def test_the_policy_allows_five_requests_per_ten_seconds(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    arrivals: list[float] = []

    def respond(_request: httpx2.Request) -> httpx2.Response:
        arrivals.append(clock.now)
        return httpx2.Response(500)

    client = stubbed_client(database, clock, wall, respond)
    for index in range(6):
        with pytest.raises(ProviderError):
            await client.get_series(str(index))

    assert arrivals == [0, 0, 0, 0, 0, 10]
