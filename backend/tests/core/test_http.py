import asyncio
import gzip
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from email.utils import format_datetime

import httpx2
import pytest
from sqlalchemy import select

from tests.helpers.clock import FakeClock
from tomarr.core.database import Database
from tomarr.core.errors import RateLimited
from tomarr.core.http import HttpClientFactory, HttpPolicy, safe_url, split_url_credentials
from tomarr.domain.http_cache import HttpCacheEntry

BASE_URL = "https://api.example.test"
CACHED = HttpPolicy("MangaBaka", requests=10, interval=1, cache_ttl=60)
UNCACHED = HttpPolicy("Prowlarr", requests=10, interval=1)
WALL_START = 1_700_000_000.0


class Server:
    """The inner transport's handler: records each request and the limiter clock when it
    arrived, then answers with `respond`."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.requests: list[httpx2.Request] = []
        self.arrivals: list[tuple[str, float]] = []
        self.respond = lambda _request: httpx2.Response(200, json={"ok": True})

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        self.arrivals.append((request.url.path, self.clock.now))
        return self.respond(request)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def wall() -> FakeClock:
    wall = FakeClock()
    wall.now = WALL_START
    return wall


@pytest.fixture
def server(clock: FakeClock) -> Server:
    return Server(clock)


def make_factory(
    database: Database,
    clock: FakeClock,
    wall: FakeClock,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> HttpClientFactory:
    return HttpClientFactory(
        database.session_factory, transport=transport, clock=clock, sleep=clock.sleep, now=wall
    )


@pytest.fixture
def factory(
    database: Database, clock: FakeClock, wall: FakeClock, server: Server
) -> HttpClientFactory:
    return make_factory(database, clock, wall, httpx2.MockTransport(server))


async def cache_rows(database: Database) -> list[HttpCacheEntry]:
    async with database.session_factory() as session:
        return list((await session.scalars(select(HttpCacheEntry))).all())


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://u:p@host:8080/a?k=v", "https://host:8080/a?k=v"),
        ("https://host:8080/a?k=v", "https://host:8080/a?k=v"),
        ("http://u:p@[::1]:9696/api", "http://[::1]:9696/api"),
        ("https://u:@host/a", "https://host/a"),
    ],
)
def test_safe_url_drops_userinfo(url: str, expected: str) -> None:
    assert safe_url(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://u:p@host:8080/a?k=v", ("https://host:8080/a?k=v", "u", "p")),
        ("https://host:8080/a?k=v", ("https://host:8080/a?k=v", None, None)),
        ("http://u:p@[::1]:9696/api", ("http://[::1]:9696/api", "u", "p")),
        ("https://u:@host/a", ("https://host/a", "u", "")),
        ("https://u:p%40ss@host/a", ("https://host/a", "u", "p@ss")),
    ],
)
def test_split_url_credentials(url: str, expected: tuple[str, str | None, str | None]) -> None:
    assert split_url_credentials(url) == expected


@pytest.mark.parametrize("base_url", ["https://reader:hunter2@host", "https://:hunter2@host"])
def test_client_rejects_a_base_url_with_userinfo(factory: HttpClientFactory, base_url: str) -> None:
    with pytest.raises(ValueError) as raised:
        factory.client(UNCACHED, base_url=base_url)

    assert "hunter2" not in str(raised.value)


async def test_basic_auth_travels_in_a_header_and_not_in_the_url(
    factory: HttpClientFactory, server: Server
) -> None:
    async with factory.client(UNCACHED, base_url=BASE_URL, auth=("reader", "hunter2")) as client:
        await client.get("/v1/items")

    [request] = server.requests
    assert request.headers["authorization"].startswith("Basic ")
    assert "reader" not in str(request.url)
    assert "hunter2" not in str(request.url)


async def test_api_key_header_travels_in_a_header_and_not_in_the_url(
    factory: HttpClientFactory, server: Server
) -> None:
    async with factory.client(UNCACHED, base_url=BASE_URL, headers={"X-Api-Key": "k3y"}) as client:
        await client.get("/v1/items")

    [request] = server.requests
    assert request.headers["x-api-key"] == "k3y"
    assert "k3y" not in str(request.url)


@pytest.mark.vcr
async def test_second_get_is_served_from_the_cache_without_a_network_call(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    # No transport is passed, so the factory uses httpx2.AsyncHTTPTransport, which vcr patches.
    # The cassette holds one interaction, and vcr raises on a second network call.
    factory = make_factory(database, clock, wall)

    async with factory.client(CACHED, base_url=BASE_URL) as client:
        first = await client.get("/v1/items")
        second = await client.get("/v1/items")

    assert first.json() == second.json() == {"items": [{"id": 1, "title": "Dandadan"}]}


async def test_get_after_the_ttl_goes_to_the_network_again(
    factory: HttpClientFactory, server: Server, wall: FakeClock
) -> None:
    async with factory.client(CACHED, base_url=BASE_URL) as client:
        await client.get("/v1/items")
        wall.now += 59
        await client.get("/v1/items")
        wall.now += 1
        await client.get("/v1/items")

    assert len(server.requests) == 2


async def test_post_is_never_cached(factory: HttpClientFactory, server: Server) -> None:
    async with factory.client(CACHED, base_url=BASE_URL) as client:
        await client.post("/graphql", json={"query": "{ a }"})
        await client.post("/graphql", json={"query": "{ a }"})

    assert len(server.requests) == 2


async def test_non_200_response_is_never_cached(
    factory: HttpClientFactory, server: Server, database: Database
) -> None:
    server.respond = lambda _request: httpx2.Response(404, json={"error": "missing"})

    async with factory.client(CACHED, base_url=BASE_URL) as client:
        await client.get("/v1/items")
        response = await client.get("/v1/items")

    assert response.status_code == 404
    assert len(server.requests) == 2
    assert await cache_rows(database) == []


async def test_policy_without_a_ttl_caches_nothing(
    factory: HttpClientFactory, server: Server, database: Database
) -> None:
    async with factory.client(UNCACHED, base_url=BASE_URL) as client:
        await client.get("/v1/items")
        await client.get("/v1/items")

    assert len(server.requests) == 2
    assert await cache_rows(database) == []


async def test_gzip_body_is_stored_raw_and_decoded_once_on_replay(
    factory: HttpClientFactory, server: Server, database: Database
) -> None:
    compressed = gzip.compress(b'{"ok": true}')
    server.respond = lambda _request: httpx2.Response(
        200,
        headers={"content-encoding": "gzip", "content-type": "application/json"},
        stream=httpx2.ByteStream(compressed),
    )

    async with factory.client(CACHED, base_url=BASE_URL) as client:
        live = await client.get("/v1/items")
        replayed = await client.get("/v1/items")

    assert live.json() == replayed.json() == {"ok": True}
    assert replayed.headers["content-encoding"] == "gzip"
    assert len(server.requests) == 1
    [row] = await cache_rows(database)
    assert row.body == compressed


class BrokenStream(httpx2.AsyncByteStream):
    """A body that drops partway through, like a connection lost mid-read."""

    def __init__(self) -> None:
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b'{"items": '
        raise httpx2.ReadError("connection dropped")

    async def aclose(self) -> None:
        self.closed = True


async def test_body_read_error_closes_the_response_and_propagates(
    factory: HttpClientFactory, server: Server, database: Database
) -> None:
    stream = BrokenStream()
    server.respond = lambda _request: httpx2.Response(200, stream=stream)

    async with factory.client(CACHED, base_url=BASE_URL) as client:
        with pytest.raises(httpx2.ReadError):
            await client.get("/v1/items")

    assert stream.closed
    assert await cache_rows(database) == []


async def test_gathered_calls_reach_the_network_one_interval_apart(
    factory: HttpClientFactory, server: Server
) -> None:
    policy = HttpPolicy("MangaBaka", requests=1, interval=10)

    async with factory.client(policy, base_url=BASE_URL) as client:
        await asyncio.gather(client.get("/a"), client.get("/b"))

    assert server.arrivals == [("/a", 0), ("/b", 10)]


async def test_cache_hit_does_not_use_a_limiter_slot(
    factory: HttpClientFactory, server: Server, clock: FakeClock
) -> None:
    policy = HttpPolicy("MangaBaka", requests=1, interval=10, cache_ttl=60)

    async with factory.client(policy, base_url=BASE_URL) as client:
        await client.get("/a")
        await client.get("/a")

    assert clock.now == 0
    assert len(server.requests) == 1


async def test_clients_with_the_same_name_share_a_limiter(
    factory: HttpClientFactory, server: Server
) -> None:
    policy = HttpPolicy("MangaBaka", requests=1, interval=10)

    async with (
        factory.client(policy, base_url=BASE_URL) as one,
        factory.client(policy, base_url=BASE_URL) as two,
    ):
        await asyncio.gather(one.get("/a"), two.get("/b"))

    assert server.arrivals == [("/a", 0), ("/b", 10)]


async def test_clients_with_different_names_do_not_share_a_limiter(
    factory: HttpClientFactory, server: Server
) -> None:
    mangabaka = HttpPolicy("MangaBaka", requests=1, interval=10)
    anilist = HttpPolicy("AniList", requests=1, interval=10)

    async with (
        factory.client(mangabaka, base_url=BASE_URL) as one,
        factory.client(anilist, base_url=BASE_URL) as two,
    ):
        await asyncio.gather(one.get("/a"), two.get("/b"))

    assert server.arrivals == [("/a", 0), ("/b", 0)]


def http_date(timestamp: float) -> str:
    return format_datetime(datetime.fromtimestamp(timestamp, UTC), usegmt=True)


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Retry-After": "7"}, 7.0),
        ({"Retry-After": http_date(WALL_START + 30)}, 30.0),
        ({"Retry-After": http_date(WALL_START - 30)}, 0.0),
        ({}, None),
        ({"Retry-After": "soon"}, None),
        ({"Retry-After": "-5"}, 0.0),
    ],
)
async def test_429_raises_rate_limited_with_the_retry_after_delay(
    factory: HttpClientFactory,
    server: Server,
    database: Database,
    headers: dict[str, str],
    expected: float | None,
) -> None:
    server.respond = lambda _request: httpx2.Response(429, headers=headers)

    async with factory.client(CACHED, base_url=BASE_URL) as client:
        with pytest.raises(RateLimited) as raised:
            await client.get("/v1/items")

    assert raised.value.service == "MangaBaka"
    assert raised.value.retry_after == expected
    assert await cache_rows(database) == []


async def test_429_logs_one_warning_with_the_adapter_and_the_delay(
    factory: HttpClientFactory, server: Server, caplog: pytest.LogCaptureFixture
) -> None:
    server.respond = lambda _request: httpx2.Response(429, headers={"Retry-After": "7"})

    async with factory.client(CACHED, base_url=BASE_URL) as client:
        with pytest.raises(RateLimited):
            await client.get("/v1/items")

    [record] = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert record.levelno == logging.WARNING
    assert "MangaBaka" in record.getMessage()
    assert "7 seconds" in record.getMessage()


async def test_log_lines_from_a_call_carry_the_adapter_name_and_no_url_or_credential(
    factory: HttpClientFactory, server: Server, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    leaks = ["api.example.test", "/v1/items", "q-s3cret", "hunter2", "k3y"]

    async with factory.client(
        CACHED, base_url=BASE_URL, auth=("reader", "hunter2"), headers={"X-Api-Key": "k3y"}
    ) as client:
        await client.get("/v1/items?token=q-s3cret")
        await client.get("/v1/items?token=q-s3cret")
        server.respond = lambda _request: httpx2.Response(429)
        with pytest.raises(RateLimited):
            await client.get("/v1/items?page=2&token=q-s3cret")

    messages = [record.getMessage() for record in caplog.records]
    assert any("MangaBaka" in message for message in messages)
    leaked = [leak for leak in leaks for message in messages if leak in message]
    assert leaked == []
