from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from tests.helpers.cassettes import recorded_response_body
from tomarr.domain.external_id import Provider
from tomarr.domain.series import Format
from tomarr.providers.mangabaka.mapper import parse_search, parse_series

CASSETTES = (
    Path(__file__).parents[2] / "fixtures" / "cassettes" / "providers" / "mangabaka" / "test_client"
)

Payload = dict[str, object]


def recorded_body(name: str) -> Payload:
    return cast(Payload, recorded_response_body(CASSETTES / f"{name}.yaml"))


@pytest.fixture
def search_body() -> Payload:
    return recorded_body("test_search_returns_candidates_with_external_ids")


@pytest.fixture
def series_body() -> Payload:
    return recorded_body("test_get_series_returns_the_series_by_its_id")


def with_changes(body: Payload, index: int, **changes: object) -> Payload:
    results = cast(list[Payload], body["data"])
    results[index] = {**results[index], **changes}
    return body


def test_search_maps_every_recorded_result(search_body: Payload) -> None:
    candidates = parse_search(search_body)

    assert [candidate.provider_id for candidate in candidates] == ["1995", "100730", "64805"]
    assert {candidate.provider for candidate in candidates} == {Provider.MANGABAKA}


def test_frieren_candidate_carries_what_the_recording_shows(search_body: Payload) -> None:
    frieren = parse_search(search_body)[0]

    assert frieren.title == "Frieren: Beyond Journey\u2019s End"
    assert frieren.format is Format.MANGA
    assert frieren.status == "hiatus"
    assert frieren.total_volumes == Decimal(15)
    assert frieren.total_chapters == Decimal(147)


def test_external_ids_hold_the_anilist_and_manga_updates_ids_as_strings(
    search_body: Payload,
) -> None:
    frieren = parse_search(search_body)[0]

    assert frieren.external_ids == {Provider.ANILIST: "118586", Provider.MANGAUPDATES: "ugf5dzu"}


def test_only_anilist_and_manga_updates_are_mapped(search_body: Payload) -> None:
    # The recording also holds my_anime_list, kitsu, anime_planet and others.
    for candidate in parse_search(search_body):
        assert set(candidate.external_ids) == {Provider.ANILIST, Provider.MANGAUPDATES}


def test_a_source_entry_with_a_null_id_is_skipped(search_body: Payload) -> None:
    series = cast(list[Payload], search_body["data"])[0]
    source = cast(Payload, series["source"])
    body = with_changes(search_body, 0, source={**source, "anilist": {"id": None, "rating": None}})

    assert parse_search(body)[0].external_ids == {Provider.MANGAUPDATES: "ugf5dzu"}


def test_aliases_are_the_other_titles_without_repeats(search_body: Payload) -> None:
    frieren = parse_search(search_body)[0]

    assert "葬送のフリーレン" in frieren.aliases
    assert "Sousou no Frieren" in frieren.aliases
    assert len(set(frieren.aliases)) == len(frieren.aliases)


def test_the_title_is_not_listed_as_its_own_alias(search_body: Payload) -> None:
    body = with_changes(search_body, 0, title="Sousou no Frieren")

    frieren = parse_search(body)[0]

    assert frieren.title == "Sousou no Frieren"
    assert "Sousou no Frieren" not in frieren.aliases
    assert "葬送のフリーレン" in frieren.aliases


@pytest.mark.parametrize(
    ("series_type", "expected"),
    [("manga", Format.MANGA), ("manhwa", Format.MANHWA), ("novel", None), ("oel", None)],
)
def test_type_maps_to_format(
    search_body: Payload, series_type: str, expected: Format | None
) -> None:
    body = with_changes(search_body, 0, type=series_type)

    assert parse_search(body)[0].format is expected


def test_the_recorded_novel_has_no_format(search_body: Payload) -> None:
    novel = parse_search(search_body)[1]

    assert novel.format is None
    assert novel.status == "completed"
    assert novel.total_volumes == Decimal(2)
    assert novel.total_chapters == Decimal(10)


def test_totals_parse_as_decimals_and_null_stays_unknown(search_body: Payload) -> None:
    body = with_changes(search_body, 0, final_volume=None, total_chapters="139.5")
    body = with_changes(body, 1, final_volume="14.5")

    frieren, novel, _ = parse_search(body)

    assert frieren.total_volumes is None
    assert novel.total_volumes == Decimal("14.5")
    assert frieren.total_chapters == Decimal("139.5")


def test_get_series_maps_the_same_series_as_search(
    search_body: Payload, series_body: Payload
) -> None:
    assert parse_series(series_body) == parse_search(search_body)[0]


@pytest.mark.parametrize("data", ["nope", None, {"id": 1995}])
def test_a_series_that_does_not_match_the_shape_is_refused(
    series_body: Payload, data: object
) -> None:
    with pytest.raises(ValidationError):
        parse_series({**series_body, "data": data})
