from collections.abc import Callable
from decimal import Decimal
from importlib.metadata import version

import httpx2
import pytest

from tests.helpers.clock import FakeClock
from tests.helpers.http import make_factory
from tomarr.core.database import Database
from tomarr.core.errors import ProviderError, RateLimited
from tomarr.providers.base import SeriesLatestChapter
from tomarr.providers.mangaupdates.client import MangaUpdatesClient

FRIEREN_ID = "ugf5dzu"
FRIEREN_PATH = "/v1/series/66296374554"
FRIEREN_BODY = {"series_id": 66296374554, "latest_chapter": 147}


def stubbed_client(
    database: Database,
    clock: FakeClock,
    wall: FakeClock,
    respond: Callable[[httpx2.Request], httpx2.Response],
) -> MangaUpdatesClient:
    transport = httpx2.MockTransport(respond)
    return MangaUpdatesClient(make_factory(database, clock, wall, transport))


@pytest.mark.vcr
async def test_get_latest_chapter_returns_the_latest_chapter_of_a_series(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    client = MangaUpdatesClient(make_factory(database, clock, wall))

    latest_chapter = await client.get_latest_chapter(FRIEREN_ID)

    assert latest_chapter == Decimal(147)


def test_client_satisfies_the_series_latest_chapter_protocol(database: Database) -> None:
    client = MangaUpdatesClient(make_factory(database, FakeClock(), FakeClock()))

    # An assignment so pyright checks the method signature. isinstance only checks the name.
    latest_chapter: SeriesLatestChapter = client

    assert isinstance(latest_chapter, SeriesLatestChapter)


async def test_the_request_asks_for_the_series_by_its_base_36_number_as_tomarr(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(500)

    client = stubbed_client(database, clock, wall, respond)
    with pytest.raises(ProviderError):
        await client.get_latest_chapter(FRIEREN_ID)

    (request,) = seen
    assert request.method == "GET"
    assert request.url.host == "api.mangaupdates.com"
    assert request.url.path == FRIEREN_PATH
    assert request.headers["user-agent"] == (
        f"Tomarr/{version('tomarr')} (+https://github.com/serfoll/tomarr)"
    )
    assert "authorization" not in request.headers


@pytest.mark.parametrize(
    "provider_id",
    [
        "",
        "UGF5DZU",
        "../series",
        "1/2",
        "١٢",
        " ugf5dzu",
        "ugf5dzu\n",
    ],
)
async def test_an_id_that_is_not_base_36_is_refused_without_sending_it(
    database: Database, clock: FakeClock, wall: FakeClock, provider_id: str
) -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(500)

    client = stubbed_client(database, clock, wall, respond)

    with pytest.raises(ValueError, match="MangaUpdates"):
        await client.get_latest_chapter(provider_id)

    assert seen == []


async def test_a_429_raises_rate_limited_with_the_retry_after(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    client = stubbed_client(
        database, clock, wall, lambda _request: httpx2.Response(429, headers={"Retry-After": "10"})
    )

    with pytest.raises(RateLimited) as raised:
        await client.get_latest_chapter(FRIEREN_ID)

    assert raised.value.service == "MangaUpdates"
    assert raised.value.retry_after == 10


@pytest.mark.parametrize("status", [404, 500, 503])
async def test_a_non_200_status_is_refused_even_when_the_body_has_the_right_shape(
    database: Database, clock: FakeClock, wall: FakeClock, status: int
) -> None:
    client = stubbed_client(
        database, clock, wall, lambda _r: httpx2.Response(status, json=FRIEREN_BODY)
    )

    with pytest.raises(ProviderError) as raised:
        await client.get_latest_chapter(FRIEREN_ID)

    assert raised.value.provider == "MangaUpdates"
    assert raised.value.status == status


UNUSABLE_BODIES = [
    pytest.param(httpx2.Response(200, content=b"<html>maintenance</html>"), id="html"),
    pytest.param(httpx2.Response(200, json={"latest_chapter": "147"}), id="wrong-shape"),
    pytest.param(httpx2.Response(200, json=["not", "an", "object"]), id="not-an-object"),
]


@pytest.mark.parametrize("unusable", UNUSABLE_BODIES)
async def test_an_unusable_200_raises_provider_error_and_is_not_cached(
    database: Database, clock: FakeClock, wall: FakeClock, unusable: httpx2.Response
) -> None:
    responses = [unusable, httpx2.Response(200, json=FRIEREN_BODY)]
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return responses[len(seen) - 1]

    client = stubbed_client(database, clock, wall, respond)

    with pytest.raises(ProviderError) as raised:
        await client.get_latest_chapter(FRIEREN_ID)
    result = await client.get_latest_chapter(FRIEREN_ID)

    assert raised.value.status == 200
    assert result == Decimal(147)
    assert len(seen) == 2


async def test_a_response_is_cached_for_an_hour(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=FRIEREN_BODY)

    client = stubbed_client(database, clock, wall, respond)

    await client.get_latest_chapter(FRIEREN_ID)
    wall.now += 60
    await client.get_latest_chapter(FRIEREN_ID)
    assert len(seen) == 1

    wall.now += 3541
    await client.get_latest_chapter(FRIEREN_ID)
    assert len(seen) == 2


async def test_the_policy_allows_one_request_per_second(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    arrivals: list[float] = []

    def respond(_request: httpx2.Request) -> httpx2.Response:
        arrivals.append(clock.now)
        return httpx2.Response(500)

    client = stubbed_client(database, clock, wall, respond)
    for _ in range(3):
        with pytest.raises(ProviderError):
            await client.get_latest_chapter(FRIEREN_ID)

    assert arrivals == [0, 1, 2]
