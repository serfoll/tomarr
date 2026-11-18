import logging
from collections.abc import Callable
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path
from urllib.parse import parse_qs

import httpx2
import pytest

from tests.helpers.cassettes import recorded_response_body
from tests.helpers.clock import FakeClock
from tests.helpers.http import make_factory
from tomarr.core.database import Database
from tomarr.core.errors import ProviderError, RateLimited
from tomarr.providers.base import SeriesVolumes
from tomarr.providers.mangadex.client import MangaDexClient

DANDADAN_ID = "68112dc1-2b80-4f20-beb8-2f2a8716a430"
RECORDED_DANDADAN = (
    Path(__file__).parents[2]
    / "fixtures"
    / "cassettes"
    / "providers"
    / "mangadex"
    / "test_client"
    / "test_get_volume_chapters_returns_the_volumes_of_a_series.yaml"
)


def stubbed_client(
    database: Database,
    clock: FakeClock,
    wall: FakeClock,
    respond: Callable[[httpx2.Request], httpx2.Response],
) -> MangaDexClient:
    transport = httpx2.MockTransport(respond)
    return MangaDexClient(make_factory(database, clock, wall, transport))


@pytest.mark.vcr
async def test_get_volume_chapters_returns_the_volumes_of_a_series(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    client = MangaDexClient(make_factory(database, clock, wall))

    volumes = await client.get_volume_chapters(DANDADAN_ID)

    assert set(volumes) == {None, *map(Decimal, [*range(1, 19), 23, 26])}
    assert volumes[Decimal(23)] == {Decimal("201.5")}
    assert len(volumes[None]) == 105


def test_client_satisfies_the_series_volumes_protocol(database: Database) -> None:
    client = MangaDexClient(make_factory(database, FakeClock(), FakeClock()))

    # An assignment so pyright checks the method signature. isinstance only checks the name.
    volumes: SeriesVolumes = client

    assert isinstance(volumes, SeriesVolumes)


async def test_the_request_asks_for_unavailable_chapters_in_every_language_as_tomarr(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(500)

    client = stubbed_client(database, clock, wall, respond)
    with pytest.raises(ProviderError):
        await client.get_volume_chapters(DANDADAN_ID)

    (request,) = seen
    assert request.method == "GET"
    assert request.url.host == "api.mangadex.org"
    assert request.url.path == f"/manga/{DANDADAN_ID}/aggregate"
    assert parse_qs(request.url.query.decode()) == {"includeUnavailable": ["1"]}
    assert request.headers["user-agent"] == (
        f"Tomarr/{version('tomarr')} (+https://github.com/serfoll/tomarr)"
    )
    assert "authorization" not in request.headers


@pytest.mark.parametrize(
    "provider_id",
    [
        "",
        "1995",
        f"{DANDADAN_ID}?limit=1",
        f"{DANDADAN_ID}/../chapter",
        "../manga",
        f"{DANDADAN_ID}\n",
        f"{{{DANDADAN_ID}}}",
        DANDADAN_ID.replace("-", ""),
    ],
)
async def test_an_id_that_is_not_a_uuid_is_refused_without_sending_it(
    database: Database, clock: FakeClock, wall: FakeClock, provider_id: str
) -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(500)

    client = stubbed_client(database, clock, wall, respond)

    with pytest.raises(ValueError, match="MangaDex"):
        await client.get_volume_chapters(provider_id)

    assert seen == []


async def test_a_429_raises_rate_limited_with_the_retry_after(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    client = stubbed_client(
        database, clock, wall, lambda _request: httpx2.Response(429, headers={"Retry-After": "10"})
    )

    with pytest.raises(RateLimited) as raised:
        await client.get_volume_chapters(DANDADAN_ID)

    assert raised.value.service == "MangaDex"
    assert raised.value.retry_after == 10


@pytest.mark.parametrize("status", [403, 404, 500, 503, 301])
async def test_a_non_200_status_is_refused_even_when_the_body_has_the_right_shape(
    database: Database, clock: FakeClock, wall: FakeClock, status: int
) -> None:
    body = recorded_response_body(RECORDED_DANDADAN)
    client = stubbed_client(database, clock, wall, lambda _r: httpx2.Response(status, json=body))

    with pytest.raises(ProviderError) as raised:
        await client.get_volume_chapters(DANDADAN_ID)

    assert raised.value.provider == "MangaDex"
    assert raised.value.status == status
    assert "mangadex.org" not in str(raised.value)
    assert DANDADAN_ID not in str(raised.value)


UNUSABLE_BODIES = [
    pytest.param(httpx2.Response(200, content=b"<html>maintenance</html>"), id="html"),
    pytest.param(httpx2.Response(200, content=b"\xff\xfe\x00"), id="not-utf8"),
    pytest.param(httpx2.Response(200, content=b"[" * 200_000), id="too-deep"),
    pytest.param(httpx2.Response(200, json={"volumes": "s3cr3t body"}), id="wrong-shape"),
    pytest.param(httpx2.Response(200, json=["not", "an", "object"]), id="not-an-object"),
]


@pytest.mark.parametrize("unusable", UNUSABLE_BODIES)
async def test_an_unusable_200_raises_provider_error_and_is_not_cached(
    database: Database, clock: FakeClock, wall: FakeClock, unusable: httpx2.Response
) -> None:
    good = httpx2.Response(200, json=recorded_response_body(RECORDED_DANDADAN))
    responses = [unusable, good]
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return responses[len(seen) - 1]

    client = stubbed_client(database, clock, wall, respond)

    with pytest.raises(ProviderError) as raised:
        await client.get_volume_chapters(DANDADAN_ID)
    result = await client.get_volume_chapters(DANDADAN_ID)

    assert raised.value.status == 200
    assert result
    assert len(seen) == 2


async def test_a_body_that_does_not_match_the_shape_logs_where_without_the_body(
    database: Database, clock: FakeClock, wall: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    client = stubbed_client(
        database, clock, wall, lambda _r: httpx2.Response(200, json={"volumes": "s3cr3t body"})
    )

    with caplog.at_level(logging.WARNING), pytest.raises(ProviderError):
        await client.get_volume_chapters(DANDADAN_ID)

    logged = [record for record in caplog.records if record.name.startswith("tomarr.providers")]
    assert [record.levelno for record in logged] == [logging.WARNING]
    message = logged[0].getMessage()
    assert "MangaDex" in message
    assert "volumes" in message
    assert "s3cr3t" not in message
    assert DANDADAN_ID not in message
    assert "mangadex.org" not in message


async def test_a_second_call_inside_the_ttl_is_answered_from_the_cache(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    body = recorded_response_body(RECORDED_DANDADAN)
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=body)

    client = stubbed_client(database, clock, wall, respond)

    first = await client.get_volume_chapters(DANDADAN_ID)
    wall.now += 60
    second = await client.get_volume_chapters(DANDADAN_ID)

    assert first == second
    assert len(seen) == 1


async def test_the_cache_expires_after_an_hour(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    body = recorded_response_body(RECORDED_DANDADAN)
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=body)

    client = stubbed_client(database, clock, wall, respond)

    await client.get_volume_chapters(DANDADAN_ID)
    wall.now += 3601
    await client.get_volume_chapters(DANDADAN_ID)

    assert len(seen) == 2


async def test_the_policy_allows_five_requests_per_second(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    arrivals: list[float] = []

    def respond(_request: httpx2.Request) -> httpx2.Response:
        arrivals.append(clock.now)
        return httpx2.Response(500)

    client = stubbed_client(database, clock, wall, respond)
    for _ in range(6):
        with pytest.raises(ProviderError):
            await client.get_volume_chapters(DANDADAN_ID)

    assert arrivals == [0, 0, 0, 0, 0, 1]
