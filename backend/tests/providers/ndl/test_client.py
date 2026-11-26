from collections.abc import Callable
from decimal import Decimal
from importlib.metadata import version

import httpx2
import pytest

from tests.helpers.clock import FakeClock
from tests.helpers.http import make_factory
from tomarr.core.database import Database
from tomarr.core.errors import ProviderError, RateLimited
from tomarr.matching.thresholds import Thresholds
from tomarr.providers.base import SeriesVolumeMetadata, VolumeMetadata
from tomarr.providers.ndl.client import NdlClient

THRESHOLDS = Thresholds(high=95, medium=85)
SERIES = "葬送のフリーレン"
FEED = (
    '<rss xmlns:dc="http://purl.org/dc/elements/1.1/"'
    ' xmlns:dcndl="http://ndl.go.jp/dcndl/terms/"'
    ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="2.0"><channel>'
    f"<item><title>{SERIES}</title><dcndl:volume>VOL.1</dcndl:volume>"
    '<dc:identifier xsi:type="dcndl:ISBN">978-4-09-850180-9</dc:identifier></item>'
    "</channel></rss>"
).encode()
VOLUME_ONE = VolumeMetadata(number=Decimal(1), isbn="9784098501809")


def stubbed_client(
    database: Database,
    clock: FakeClock,
    wall: FakeClock,
    respond: Callable[[httpx2.Request], httpx2.Response],
) -> NdlClient:
    return NdlClient(make_factory(database, clock, wall, httpx2.MockTransport(respond)))


@pytest.mark.vcr
async def test_get_volume_metadata_returns_the_volumes_of_a_series_with_isbns(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    client = NdlClient(make_factory(database, clock, wall))

    volumes = await client.get_volume_metadata(SERIES, [], THRESHOLDS)

    assert [(volume.number, volume.isbn, volume.other_isbns) for volume in volumes] == [
        (Decimal(1), "9784098501809", ()),
        (Decimal(2), "9784098501816", ()),
        (Decimal(3), "9784098502851", ()),
        (Decimal(4), "9784098504909", ()),
        (Decimal(5), "9784098506347", ()),
        (Decimal(6), "9784098507283", ("9784099430962",)),
        (Decimal(7), "9784098508761", ("9784099431044",)),
        (Decimal(8), "9784098511488", ("9784099431167",)),
        (Decimal(9), "9784098512607", ("9784099431198",)),
        (Decimal(10), "9784098517718", ("9784099431259",)),
        (Decimal(11), "9784098527694", ("9784099431327",)),
        (Decimal(12), "9784098530304", ("9784099431402",)),
        (Decimal(13), "9784098532339", ("9784099431587",)),
        (Decimal(14), "9784098540174", ("9784099431952",)),
        (Decimal(15), "9784098543465", ("9784099432201",)),
    ]


def test_client_satisfies_the_series_volume_metadata_protocol(database: Database) -> None:
    client = NdlClient(make_factory(database, FakeClock(), FakeClock()))

    # An assignment so pyright checks the method signature. isinstance only checks the name.
    volume_metadata: SeriesVolumeMetadata = client

    assert isinstance(volume_metadata, SeriesVolumeMetadata)


async def test_the_request_asks_for_manga_titled_like_the_series_as_tomarr(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(500)

    client = stubbed_client(database, clock, wall, respond)
    with pytest.raises(ProviderError):
        await client.get_volume_metadata(SERIES, [], THRESHOLDS)

    (request,) = seen
    assert request.method == "GET"
    assert request.url.host == "ndlsearch.ndl.go.jp"
    assert request.url.path == "/api/opensearch"
    assert dict(request.url.params) == {"title": SERIES, "ndc": "726", "cnt": "500"}
    assert "%E8%91%AC%E9%80%81" in request.url.query.decode()
    assert request.headers["user-agent"] == (
        f"Tomarr/{version('tomarr')} (+https://github.com/serfoll/tomarr)"
    )


async def test_a_title_cannot_add_parameters_to_the_request(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(500)

    client = stubbed_client(database, clock, wall, respond)
    with pytest.raises(ProviderError):
        await client.get_volume_metadata("a&ndc=1#b", [], THRESHOLDS)

    (request,) = seen
    assert dict(request.url.params) == {"title": "a&ndc=1#b", "ndc": "726", "cnt": "500"}


async def test_the_volumes_come_from_the_body(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    client = stubbed_client(database, clock, wall, lambda _r: httpx2.Response(200, content=FEED))

    assert await client.get_volume_metadata(SERIES, [], THRESHOLDS) == [VOLUME_ONE]


async def test_a_429_raises_rate_limited_with_the_retry_after(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    client = stubbed_client(
        database, clock, wall, lambda _r: httpx2.Response(429, headers={"Retry-After": "10"})
    )

    with pytest.raises(RateLimited) as raised:
        await client.get_volume_metadata(SERIES, [], THRESHOLDS)

    assert raised.value.service == "NDL"
    assert raised.value.retry_after == 10


@pytest.mark.parametrize("status", [400, 404, 500, 503])
async def test_a_non_200_status_is_refused_even_when_the_body_is_a_feed(
    database: Database, clock: FakeClock, wall: FakeClock, status: int
) -> None:
    client = stubbed_client(database, clock, wall, lambda _r: httpx2.Response(status, content=FEED))

    with pytest.raises(ProviderError) as raised:
        await client.get_volume_metadata(SERIES, [], THRESHOLDS)

    assert raised.value.provider == "NDL"
    assert raised.value.status == status


UNUSABLE_BODIES = [
    pytest.param(httpx2.Response(200, content=b"<html>maintenance</html>"), id="html"),
    pytest.param(httpx2.Response(200, content=b"not xml"), id="not-xml"),
    pytest.param(httpx2.Response(200, content=b""), id="empty"),
    pytest.param(
        httpx2.Response(200, content=b'<!DOCTYPE rss [<!ENTITY a "b">]><rss></rss>'), id="doctype"
    ),
]


@pytest.mark.parametrize("unusable", UNUSABLE_BODIES)
async def test_an_unusable_200_raises_provider_error_and_is_not_cached(
    database: Database, clock: FakeClock, wall: FakeClock, unusable: httpx2.Response
) -> None:
    responses = [unusable, httpx2.Response(200, content=FEED)]
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return responses[len(seen) - 1]

    client = stubbed_client(database, clock, wall, respond)

    with pytest.raises(ProviderError) as raised:
        await client.get_volume_metadata(SERIES, [], THRESHOLDS)
    result = await client.get_volume_metadata(SERIES, [], THRESHOLDS)

    assert raised.value.status == 200
    assert result == [VOLUME_ONE]
    assert len(seen) == 2


async def test_a_response_is_cached_for_an_hour(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, content=FEED)

    client = stubbed_client(database, clock, wall, respond)

    await client.get_volume_metadata(SERIES, [], THRESHOLDS)
    wall.now += 3599
    await client.get_volume_metadata(SERIES, [], THRESHOLDS)
    assert len(seen) == 1

    wall.now += 2
    await client.get_volume_metadata(SERIES, [], THRESHOLDS)
    assert len(seen) == 2


async def test_the_policy_allows_one_request_every_two_seconds(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    arrivals: list[float] = []

    def respond(_request: httpx2.Request) -> httpx2.Response:
        arrivals.append(clock.now)
        return httpx2.Response(500)

    client = stubbed_client(database, clock, wall, respond)
    for _ in range(3):
        with pytest.raises(ProviderError):
            await client.get_volume_metadata(SERIES, [], THRESHOLDS)

    assert arrivals == [0, 2, 4]


@pytest.mark.parametrize("title", ["", " ", "\u3000", " \t\n"])
async def test_a_blank_title_is_refused_before_any_request(
    database: Database, clock: FakeClock, wall: FakeClock, title: str
) -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        pytest.fail(f"A request was sent: {request.url}")

    client = stubbed_client(database, clock, wall, respond)

    with pytest.raises(ValueError, match="title"):
        await client.get_volume_metadata(title, [], THRESHOLDS)
