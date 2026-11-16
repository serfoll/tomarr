import json
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
from tomarr.providers.anilist.client import AniListClient
from tomarr.providers.base import SeriesCharacters, SeriesLookup, SeriesSearch

RECORDED_SERIES = (
    Path(__file__).parents[2]
    / "fixtures"
    / "cassettes"
    / "providers"
    / "anilist"
    / "test_client"
    / "test_get_series_returns_the_series_by_its_id.yaml"
)
FRIEREN_ID = "118586"
TITLE = "Frieren: Beyond Journey\u2019s End"
FRIEREN_COVER = (
    "https://s4.anilist.co/file/anilistcdn/media/manga/cover/large/bx118586-CXKgWikBFQgS.jpg"
)
TOWER_OF_GOD_ID = "85143"
SOUL_LAND_ID = "85446"


@pytest.fixture
def vcr_config(vcr_config: dict[str, object]) -> dict[str, object]:
    # Every AniList call is a POST to one URL, so the body tells a search from a lookup.
    return {
        **vcr_config,
        "match_on": ("method", "scheme", "host", "port", "path", "query", "body"),
    }


def stubbed_client(
    database: Database,
    clock: FakeClock,
    wall: FakeClock,
    respond: Callable[[httpx2.Request], httpx2.Response],
) -> AniListClient:
    return AniListClient(make_factory(database, clock, wall, httpx2.MockTransport(respond)))


@pytest.mark.vcr
async def test_search_returns_candidates_with_titles_format_and_cover(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    client = AniListClient(make_factory(database, clock, wall))

    candidates = await client.search("frieren", limit=3)

    assert [candidate.provider_id for candidate in candidates] == [FRIEREN_ID, "173310", "179850"]
    frieren, anthology, novel = candidates
    assert frieren.provider is Provider.ANILIST
    assert frieren.title == TITLE
    assert frieren.aliases[:2] == ("Sousou no Frieren", "葬送のフリーレン")
    assert frieren.format is Format.MANGA
    assert frieren.status == "RELEASING"
    assert frieren.total_volumes is None
    assert frieren.external_ids == {}
    assert frieren.cover_url == FRIEREN_COVER
    assert anthology.title == "Sousou no Frieren Anthology"
    assert anthology.total_volumes == Decimal(1)
    assert anthology.total_chapters == Decimal(5)
    assert novel.format is None


@pytest.mark.vcr
async def test_get_series_returns_the_series_by_its_id(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    client = AniListClient(make_factory(database, clock, wall))

    series = await client.get_series(FRIEREN_ID)

    assert series.provider_id == FRIEREN_ID
    assert series.title == TITLE
    assert series.format is Format.MANGA


@pytest.mark.vcr
@pytest.mark.parametrize(
    ("provider_id", "expected"),
    [(TOWER_OF_GOD_ID, Format.WEBTOON), (SOUL_LAND_ID, Format.MANHUA)],
    ids=["tower-of-god", "soul-land"],
)
async def test_get_series_maps_a_korean_webtoon_and_a_chinese_series(
    database: Database, clock: FakeClock, wall: FakeClock, provider_id: str, expected: Format
) -> None:
    client = AniListClient(make_factory(database, clock, wall))

    series = await client.get_series(provider_id)

    assert series.provider_id == provider_id
    assert series.format is expected


@pytest.mark.vcr
async def test_get_character_names_returns_main_characters_first(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    client = AniListClient(make_factory(database, clock, wall))

    names = await client.get_character_names(FRIEREN_ID)

    assert 0 < len(names) <= 25
    assert names[0].full == "Frieren"
    assert names[0].native == "フリーレン"


def test_client_satisfies_the_three_provider_protocols(database: Database) -> None:
    client = AniListClient(make_factory(database, FakeClock(), FakeClock()))

    # Assignments so pyright checks the method signatures. isinstance only checks the names.
    search: SeriesSearch = client
    lookup: SeriesLookup = client
    characters: SeriesCharacters = client

    assert isinstance(search, SeriesSearch)
    assert isinstance(lookup, SeriesLookup)
    assert isinstance(characters, SeriesCharacters)


type Call = Callable[[AniListClient], Awaitable[object]]

SEARCH: Call = lambda client: client.search("frieren")  # noqa: E731
LOOKUP: Call = lambda client: client.get_series(FRIEREN_ID)  # noqa: E731
CHARACTERS: Call = lambda client: client.get_character_names(FRIEREN_ID)  # noqa: E731
CALLS = [
    pytest.param(SEARCH, id="search"),
    pytest.param(LOOKUP, id="get_series"),
    pytest.param(CHARACTERS, id="get_character_names"),
]


async def test_a_429_raises_rate_limited_with_the_retry_after(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    client = stubbed_client(
        database,
        clock,
        wall,
        lambda _request: httpx2.Response(
            429,
            headers={"Retry-After": "30"},
            json={"errors": [{"message": "Too Many Requests.", "status": 429}]},
        ),
    )

    with pytest.raises(RateLimited) as raised:
        await client.search("frieren")

    assert raised.value.service == "AniList"
    assert raised.value.retry_after == 30


SECRET_TEXT = "s3cr3t body text"
UNUSABLE = [
    pytest.param(httpx2.Response(500, json={"errors": [{"message": SECRET_TEXT}]}), 500, id="500"),
    pytest.param(httpx2.Response(404, json={"errors": [{"message": SECRET_TEXT}]}), 404, id="404"),
    pytest.param(
        httpx2.Response(200, json={"errors": [{"message": SECRET_TEXT, "status": 400}]}),
        200,
        id="errors-entry",
    ),
    pytest.param(
        httpx2.Response(200, json={"errors": [{"message": SECRET_TEXT}], "data": {"Media": None}}),
        200,
        id="errors-entry-with-data",
    ),
    pytest.param(httpx2.Response(200, json={"data": None}), 200, id="data-null"),
    pytest.param(httpx2.Response(200, json={"data": {"Page": SECRET_TEXT}}), 200, id="wrong-shape"),
    pytest.param(httpx2.Response(200, json=[SECRET_TEXT]), 200, id="not-an-object"),
    pytest.param(httpx2.Response(200, content=b"<html>maintenance</html>"), 200, id="html"),
    pytest.param(httpx2.Response(200, content=b"\xff\xfe\x00"), 200, id="not-utf8"),
    pytest.param(httpx2.Response(200, content=b"[" * 200_000), 200, id="too-deep"),
]


@pytest.mark.parametrize("call", CALLS)
@pytest.mark.parametrize(("response", "status"), UNUSABLE)
async def test_an_unusable_response_raises_provider_error_without_any_body_text(
    database: Database,
    clock: FakeClock,
    wall: FakeClock,
    call: Call,
    response: httpx2.Response,
    status: int,
) -> None:
    client = stubbed_client(database, clock, wall, lambda _request: response)

    with pytest.raises(ProviderError) as raised:
        await call(client)

    assert raised.value.provider == "AniList"
    assert raised.value.status == status
    assert SECRET_TEXT not in str(raised.value)
    assert "anilist.co" not in str(raised.value)
    assert "frieren" not in str(raised.value)


@pytest.mark.parametrize("status", [503, 404, 301])
async def test_a_non_200_status_is_refused_even_when_the_body_has_the_right_shape(
    database: Database, clock: FakeClock, wall: FakeClock, status: int
) -> None:
    body = recorded_response_body(RECORDED_SERIES)
    client = stubbed_client(database, clock, wall, lambda _r: httpx2.Response(status, json=body))

    with pytest.raises(ProviderError) as raised:
        await client.get_series(FRIEREN_ID)

    assert raised.value.status == status


async def test_a_graphql_error_in_a_200_logs_where_without_the_message(
    database: Database, clock: FakeClock, wall: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    client = stubbed_client(
        database,
        clock,
        wall,
        lambda _r: httpx2.Response(200, json={"errors": [{"message": SECRET_TEXT}], "data": None}),
    )

    with caplog.at_level(logging.WARNING), pytest.raises(ProviderError):
        await client.get_series(FRIEREN_ID)

    logged = [record for record in caplog.records if record.name.startswith("tomarr.providers")]
    assert [record.levelno for record in logged] == [logging.WARNING]
    message = logged[0].getMessage()
    assert "AniList" in message
    assert "errors" in message
    assert SECRET_TEXT not in message
    assert "anilist.co" not in message


@pytest.mark.parametrize("provider_id", ["", "12x", "1/../2", "-1", "1 2", "\u0661", "1.5"])
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda client, pid: client.get_series(pid), id="get_series"),
        pytest.param(lambda client, pid: client.get_character_names(pid), id="characters"),
    ],
)
async def test_an_id_that_is_not_ascii_digits_is_refused_without_sending_it(
    database: Database,
    clock: FakeClock,
    wall: FakeClock,
    call: Callable[[AniListClient, str], Awaitable[object]],
    provider_id: str,
) -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(500)

    client = stubbed_client(database, clock, wall, respond)

    with pytest.raises(ValueError, match="digits") as raised:
        await call(client, provider_id)

    assert seen == []
    if provider_id:
        assert provider_id not in str(raised.value)


async def test_a_repeated_search_makes_two_requests(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"data": {"Page": {"media": []}}})

    client = stubbed_client(database, clock, wall, respond)

    first = await client.search("frieren")
    second = await client.search("frieren")

    assert first == second == []
    assert len(seen) == 2


async def test_requests_are_posts_to_the_endpoint_with_the_values_in_variables(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(500)

    client = stubbed_client(database, clock, wall, respond)
    hostile = 'x") { id } #'
    for call in (
        lambda: client.search(hostile, limit=5),
        lambda: client.get_series(FRIEREN_ID),
        lambda: client.get_character_names(FRIEREN_ID),
    ):
        with pytest.raises(ProviderError):
            await call()

    bodies = [cast(dict[str, object], json.loads(request.content)) for request in seen]
    assert [request.method for request in seen] == ["POST"] * 3
    assert {str(request.url) for request in seen} == {"https://graphql.anilist.co/"}
    assert [set(body) for body in bodies] == [{"query", "variables"}] * 3
    assert [body["variables"] for body in bodies] == [
        {"search": hostile, "perPage": 5},
        {"id": int(FRIEREN_ID)},
        {"id": int(FRIEREN_ID)},
    ]
    for body in bodies:
        assert hostile not in cast(str, body["query"])
        assert FRIEREN_ID not in cast(str, body["query"])
    assert all("authorization" not in request.headers for request in seen)
    assert all("x-api-key" not in request.headers for request in seen)


async def test_the_policy_allows_thirty_requests_per_sixty_seconds(
    database: Database, clock: FakeClock, wall: FakeClock
) -> None:
    arrivals: list[float] = []

    def respond(_request: httpx2.Request) -> httpx2.Response:
        arrivals.append(clock.now)
        return httpx2.Response(500)

    client = stubbed_client(database, clock, wall, respond)
    for _ in range(31):
        with pytest.raises(ProviderError):
            await client.get_series(FRIEREN_ID)

    assert arrivals == [0] * 30 + [60]
