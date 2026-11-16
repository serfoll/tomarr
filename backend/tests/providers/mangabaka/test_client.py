import logging
from collections.abc import Awaitable, Callable
from decimal import Decimal
from pathlib import Path
from typing import cast

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
        (httpx2.Response(200, content=b"\xff\xfe\x00"), 200),
        (httpx2.Response(200, content=b"[" * 200_000), 200),
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


@pytest.mark.parametrize("status", [503, 404, 301])
async def test_a_non_200_status_is_refused_even_when_the_body_has_the_right_shape(
    database: Database, clock: FakeClock, wall: FakeClock, status: int
) -> None:
    body = recorded_response_body(RECORDED_SERIES)
    client = stubbed_client(database, clock, wall, lambda _r: httpx2.Response(status, json=body))

    with pytest.raises(ProviderError) as raised:
        await client.get_series("1995")

    assert raised.value.status == status


async def test_a_body_that_does_not_match_the_shape_logs_where_without_the_body(
    database: Database, clock: FakeClock, wall: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    client = stubbed_client(
        database, clock, wall, lambda _r: httpx2.Response(200, json={"data": "s3cr3t body"})
    )

    with caplog.at_level(logging.WARNING), pytest.raises(ProviderError):
        await client.search("frieren")

    logged = [record for record in caplog.records if record.name.startswith("tomarr.providers")]
    assert [record.levelno for record in logged] == [logging.WARNING]
    message = logged[0].getMessage()
    assert "MangaBaka" in message
    assert "data" in message
    assert "list_type" in message
    assert "s3cr3t" not in message
    assert "frieren" not in message
    assert "mangabaka.org" not in message


@pytest.mark.parametrize("provider_id", ["1995?limit=1", "1995/../news", "../search", "", "\u0661"])
async def test_get_series_refuses_an_id_that_is_not_digits_without_sending_it(
    database: Database, clock: FakeClock, wall: FakeClock, provider_id: str
) -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(500)

    client = stubbed_client(database, clock, wall, respond)

    with pytest.raises(ValueError, match="digits") as raised:
        await client.get_series(provider_id)

    assert seen == []
    if provider_id:
        assert provider_id not in str(raised.value)


async def test_a_repeated_search_is_answered_from_the_cache(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    series = cast(dict[str, object], recorded_response_body(RECORDED_SERIES))["data"]
    calls: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(200, json={"status": 200, "data": [series]})

    client = stubbed_client(database, clock, wall, respond)

    first = await client.search("frieren")
    wall.now += 60
    second = await client.search("frieren")

    assert first == second
    assert len(calls) == 1


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


type Call = Callable[[MangaBakaClient], Awaitable[object]]

SERIES_BODY = cast(dict[str, object], recorded_response_body(RECORDED_SERIES))
SEARCH_BODY = {"status": 200, "data": [SERIES_BODY["data"]]}
# Each call, a body it reads, and the other call's body, which it does not.
SEARCH_CALL: tuple[Call, object, object] = (
    lambda client: client.search("frieren"),
    SEARCH_BODY,
    SERIES_BODY,
)
SERIES_CALL: tuple[Call, object, object] = (
    lambda client: client.get_series("1995"),
    SERIES_BODY,
    SEARCH_BODY,
)
CALLS = [pytest.param(*SEARCH_CALL, id="search"), pytest.param(*SERIES_CALL, id="get_series")]


def sequenced_client(
    database: Database, clock: FakeClock, wall: FakeClock, responses: list[httpx2.Response]
) -> tuple[MangaBakaClient, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return responses[len(seen) - 1]

    return stubbed_client(database, clock, wall, respond), seen


@pytest.mark.parametrize(("call", "good", "other_shape"), CALLS)
@pytest.mark.parametrize(
    "unusable",
    [
        lambda _other: httpx2.Response(200, content=b"<html>maintenance</html>"),
        lambda _other: httpx2.Response(200, content=b"\xff\xfe\x00"),
        lambda _other: httpx2.Response(200, content=b"[" * 200_000),
        lambda _other: httpx2.Response(200, json={"data": "not a list or a series"}),
        lambda other: httpx2.Response(200, json=other),
    ],
    ids=["html", "not-utf8", "too-deep", "wrong-shape", "other-calls-shape"],
)
async def test_an_unusable_200_is_not_cached_so_the_next_call_reaches_the_service(
    database: Database,
    clock: FakeClock,
    wall: FakeClock,
    call: Call,
    good: object,
    other_shape: object,
    unusable: Callable[[object], httpx2.Response],
) -> None:
    client, seen = sequenced_client(
        database, clock, wall, [unusable(other_shape), httpx2.Response(200, json=good)]
    )

    with pytest.raises(ProviderError) as raised:
        await call(client)
    result = await call(client)

    assert raised.value.status == 200
    assert result
    assert len(seen) == 2


@pytest.mark.parametrize(("call", "good", "other_shape"), CALLS)
async def test_a_usable_200_is_cached_for_the_next_call(
    database: Database,
    clock: FakeClock,
    wall: FakeClock,
    call: Call,
    good: object,
    other_shape: object,
) -> None:
    client, seen = sequenced_client(database, clock, wall, [httpx2.Response(200, json=good)])

    first = await call(client)
    second = await call(client)

    assert first == second
    assert len(seen) == 1


@pytest.mark.parametrize(("call", "good", "other_shape"), CALLS)
async def test_a_refused_200_logs_once(
    database: Database,
    clock: FakeClock,
    wall: FakeClock,
    caplog: pytest.LogCaptureFixture,
    call: Call,
    good: object,
    other_shape: object,
) -> None:
    client, _seen = sequenced_client(
        database, clock, wall, [httpx2.Response(200, json=other_shape)]
    )

    with caplog.at_level(logging.WARNING), pytest.raises(ProviderError):
        await call(client)

    logged = [record for record in caplog.records if record.name.startswith("tomarr.providers")]
    assert len(logged) == 1
