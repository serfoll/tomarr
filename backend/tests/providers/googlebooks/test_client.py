import logging
import os
from collections.abc import Callable
from datetime import date
from importlib.metadata import version

import httpx2
import pytest

from tests.helpers.clock import FakeClock
from tests.helpers.http import make_factory
from tomarr.core.database import Database
from tomarr.core.errors import ProviderError, RateLimited
from tomarr.providers.base import DatePrecision, VolumeDetails, VolumeDetailsLookup
from tomarr.providers.googlebooks.client import GoogleBooksClient

KEY = "test-key-0123456789"
FRIEREN_ONE = "9784098501809"
FRIEREN_TWO = "9784098501816"


def body_for(*isbns: str) -> bytes:
    items = ",".join(
        '{"volumeInfo":{"description":"About ' + isbn + '","publishedDate":"2020-03-18",'
        '"industryIdentifiers":[{"type":"ISBN_13","identifier":"' + isbn + '"}]}}'
        for isbn in isbns
    )
    return ('{"totalItems":' + str(len(isbns)) + ',"items":[' + items + "]}").encode()


NO_MATCH = b'{"totalItems":0}'


def details_for(isbn: str) -> VolumeDetails:
    return VolumeDetails(
        synopsis=f"About {isbn}",
        release_date=date(2020, 3, 18),
        release_precision=DatePrecision.DAY,
    )


def stubbed_client(
    database: Database,
    clock: FakeClock,
    wall: FakeClock,
    respond: Callable[[httpx2.Request], httpx2.Response],
    api_key: str = KEY,
) -> GoogleBooksClient:
    transport = httpx2.MockTransport(respond)
    return GoogleBooksClient(make_factory(database, clock, wall, transport), api_key)


def by_isbn(request: httpx2.Request) -> str:
    return request.url.params["q"].removeprefix("isbn:")


def answer_with_match(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, content=body_for(by_isbn(request)))


# Test-only. The app reads the key from the google_books.api_key setting.
@pytest.mark.vcr
async def test_get_volume_details_reads_real_responses(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    key = os.environ.get("GOOGLE_BOOKS_API_KEY", "replay-key")
    client = GoogleBooksClient(make_factory(database, clock, wall), key)

    details = await client.get_volume_details(
        ["9784088851303", FRIEREN_ONE, "9784088851488", "9784866781829"]
    )

    assert list(details) == ["9784088851303", FRIEREN_ONE, "9784088851488"]
    assert details["9784088851303"].synopsis is not None
    assert details["9784088851303"].release_date == date(2026, 7, 3)
    assert details["9784088851303"].release_precision is DatePrecision.DAY
    assert details[FRIEREN_ONE].release_date == date(2020, 8, 1)
    assert details[FRIEREN_ONE].release_precision is DatePrecision.MONTH
    assert str(details[FRIEREN_ONE].cover_url).startswith("https://books.google.com/")
    assert details["9784088851488"].synopsis is None


def test_client_satisfies_the_volume_details_lookup_protocol(database: Database) -> None:
    client = GoogleBooksClient(make_factory(database, FakeClock(), FakeClock()), KEY)

    # An assignment so pyright checks the method signature. isinstance only checks the name.
    lookup: VolumeDetailsLookup = client

    assert isinstance(lookup, VolumeDetailsLookup)


async def test_each_request_searches_one_isbn_with_the_key_in_a_header(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, content=NO_MATCH)

    client = stubbed_client(database, clock, wall, respond)
    await client.get_volume_details([FRIEREN_ONE])

    (request,) = seen
    assert request.method == "GET"
    assert request.url.host == "www.googleapis.com"
    assert request.url.path == "/books/v1/volumes"
    assert request.url.params["q"] == f"isbn:{FRIEREN_ONE}"
    assert "industryIdentifiers" in request.url.params["fields"]
    assert request.headers["x-goog-api-key"] == KEY
    assert request.headers["user-agent"] == (
        f"Tomarr/{version('tomarr')} (+https://github.com/serfoll/tomarr)"
    )
    assert KEY not in str(request.url)


async def test_several_isbns_make_one_request_each_in_order(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    seen: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(by_isbn(request))
        return answer_with_match(request)

    client = stubbed_client(database, clock, wall, respond)

    details = await client.get_volume_details([FRIEREN_TWO, FRIEREN_ONE])

    assert seen == [FRIEREN_TWO, FRIEREN_ONE]
    assert details == {FRIEREN_TWO: details_for(FRIEREN_TWO), FRIEREN_ONE: details_for(FRIEREN_ONE)}


async def test_an_isbn_with_no_match_is_absent_and_raises_nothing(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        if by_isbn(request) == FRIEREN_TWO:
            return httpx2.Response(200, content=NO_MATCH)
        return answer_with_match(request)

    client = stubbed_client(database, clock, wall, respond)

    details = await client.get_volume_details([FRIEREN_ONE, FRIEREN_TWO])

    assert details == {FRIEREN_ONE: details_for(FRIEREN_ONE)}


async def test_no_isbns_make_no_request(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        pytest.fail(f"A request was sent: {request.url}")

    client = stubbed_client(database, clock, wall, respond)

    assert await client.get_volume_details([]) == {}


async def test_an_empty_key_is_refused_before_any_request(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        pytest.fail(f"A request was sent: {request.url}")

    client = stubbed_client(database, clock, wall, respond, api_key="")

    with pytest.raises(ValueError, match="key"):
        await client.get_volume_details([FRIEREN_ONE])


@pytest.mark.parametrize(
    "isbn",
    [
        "",
        "978409850180",
        "97840985018099",
        "978-4-09-850180-9",
        "97840985018x9",
        "\uff19\uff17\uff18\uff14\uff10\uff19\uff18\uff15\uff10\uff11\uff18\uff10\uff19",
    ],
)
async def test_an_isbn_that_is_not_10_or_13_digits_is_refused_before_any_request(
    database: Database, clock: FakeClock, wall: FakeClock, isbn: str
) -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        pytest.fail(f"A request was sent: {request.url}")

    client = stubbed_client(database, clock, wall, respond)

    with pytest.raises(ValueError, match="ISBN"):
        await client.get_volume_details([FRIEREN_ONE, isbn])


async def test_a_ten_digit_isbn_is_accepted(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    client = stubbed_client(
        database, clock, wall, lambda _r: httpx2.Response(200, content=NO_MATCH)
    )

    assert await client.get_volume_details(["4098501805"]) == {}


async def test_a_429_raises_rate_limited_with_the_retry_after(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    client = stubbed_client(
        database, clock, wall, lambda _r: httpx2.Response(429, headers={"Retry-After": "10"})
    )

    with pytest.raises(RateLimited) as raised:
        await client.get_volume_details([FRIEREN_ONE])

    assert raised.value.service == "Google Books"
    assert raised.value.retry_after == 10


@pytest.mark.parametrize("status", [400, 403, 404, 500, 503])
async def test_a_non_200_status_fails_the_whole_call(
    database: Database, clock: FakeClock, wall: FakeClock, status: int
) -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        if by_isbn(request) == FRIEREN_ONE:
            return answer_with_match(request)
        return httpx2.Response(status, content=body_for(by_isbn(request)))

    client = stubbed_client(database, clock, wall, respond)

    with pytest.raises(ProviderError) as raised:
        await client.get_volume_details([FRIEREN_ONE, FRIEREN_TWO])

    assert raised.value.provider == "Google Books"
    assert raised.value.status == status


UNUSABLE_BODIES = [
    pytest.param(b"<html>maintenance</html>", id="html"),
    pytest.param(b"", id="empty"),
    pytest.param(b'{"items":{"volumeInfo":1}}', id="wrong-shape"),
]


@pytest.mark.parametrize("unusable", UNUSABLE_BODIES)
async def test_an_unreadable_200_raises_provider_error_and_is_not_cached(
    database: Database, clock: FakeClock, wall: FakeClock, unusable: bytes
) -> None:
    bodies = [unusable, body_for(FRIEREN_ONE)]
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, content=bodies[len(seen) - 1])

    client = stubbed_client(database, clock, wall, respond)

    with pytest.raises(ProviderError) as raised:
        await client.get_volume_details([FRIEREN_ONE])
    result = await client.get_volume_details([FRIEREN_ONE])

    assert raised.value.status == 200
    assert result == {FRIEREN_ONE: details_for(FRIEREN_ONE)}
    assert len(seen) == 2


async def test_a_second_call_for_the_same_isbn_is_served_from_the_cache(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return answer_with_match(request)

    client = stubbed_client(database, clock, wall, respond)

    await client.get_volume_details([FRIEREN_ONE])
    wall.now += 86399
    again = await client.get_volume_details([FRIEREN_ONE])
    assert len(seen) == 1
    assert again == {FRIEREN_ONE: details_for(FRIEREN_ONE)}

    wall.now += 2
    await client.get_volume_details([FRIEREN_ONE])
    assert len(seen) == 2


async def test_the_policy_allows_one_request_a_second(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    arrivals: list[float] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        arrivals.append(clock.now)
        return answer_with_match(request)

    client = stubbed_client(database, clock, wall, respond)
    await client.get_volume_details([FRIEREN_ONE, FRIEREN_TWO, "9784098502851"])

    assert arrivals == [0, 1, 2]


@pytest.mark.parametrize(
    "respond",
    [
        pytest.param(lambda _r: httpx2.Response(403), id="403"),
        pytest.param(lambda _r: httpx2.Response(429), id="429"),
        pytest.param(lambda _r: httpx2.Response(200, content=b"nope"), id="unreadable"),
    ],
)
async def test_the_key_is_in_no_log_line_and_no_error_message(
    database: Database,
    clock: FakeClock,
    wall: FakeClock,
    caplog: pytest.LogCaptureFixture,
    respond: Callable[[httpx2.Request], httpx2.Response],
) -> None:
    caplog.set_level(logging.DEBUG)
    client = stubbed_client(database, clock, wall, respond)

    with pytest.raises((ProviderError, RateLimited)) as raised:
        await client.get_volume_details([FRIEREN_ONE])

    assert KEY not in str(raised.value)
    assert KEY not in repr(raised.value)
    assert KEY not in caplog.text
