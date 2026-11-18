from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.helpers.cassettes import recorded_response_body
from tomarr.providers.mangadex.mapper import parse_aggregate

RECORDED_DANDADAN = (
    Path(__file__).parents[2]
    / "fixtures"
    / "cassettes"
    / "providers"
    / "mangadex"
    / "test_client"
    / "test_get_volume_chapters_returns_the_volumes_of_a_series.yaml"
)


def chapter(number: str) -> dict[str, object]:
    return {
        "chapter": number,
        "id": "2179fe3e-65cd-4fb6-8e87-2b620991de51",
        "isUnavailable": False,
        "others": [],
        "count": 1,
    }


def volume(number: str, *chapters: str) -> dict[str, object]:
    return {
        "volume": number,
        "count": len(chapters),
        "chapters": {number: chapter(number) for number in chapters},
    }


def aggregate(volumes: dict[str, object]) -> dict[str, object]:
    return {"result": "ok", "volumes": volumes}


def test_the_recorded_series_maps_to_its_volumes_and_their_chapters() -> None:
    result = parse_aggregate(recorded_response_body(RECORDED_DANDADAN))

    assert set(result) == {None, *map(Decimal, [*range(1, 19), 23, 26])}
    assert result[Decimal(1)] == {Decimal(n) for n in (1, 2, 3, 4, 5)} | {Decimal("5.5")}
    assert result[Decimal(26)] == {Decimal(n) for n in (225, 226, 227, 228)}
    assert result[Decimal(23)] == {Decimal("201.5")}


def test_the_recorded_chapters_in_no_volume_are_kept_under_none() -> None:
    result = parse_aggregate(recorded_response_body(RECORDED_DANDADAN))

    in_no_volume = result[None]
    assert len(in_no_volume) == 105
    assert min(in_no_volume) == Decimal(121)
    assert max(in_no_volume) == Decimal(253)
    assert Decimal("231.1") in in_no_volume


def test_volumes_the_aggregate_does_not_list_are_left_out_not_guessed() -> None:
    result = parse_aggregate(recorded_response_body(RECORDED_DANDADAN))

    for missing in (19, 20, 21, 22, 24, 25):
        assert Decimal(missing) not in result


def test_a_volume_listed_with_no_chapters_comes_back_with_no_chapters() -> None:
    result = parse_aggregate(aggregate({"3": volume("3")}))

    assert result == {Decimal(3): frozenset()}


def test_a_decimal_chapter_is_kept_as_given() -> None:
    result = parse_aggregate(aggregate({"1": volume("1", "10", "10.5", "11")}))

    assert result == {Decimal(1): {Decimal(10), Decimal("10.5"), Decimal(11)}}
    assert Decimal("10.5") in result[Decimal(1)]


def test_chapter_zero_is_a_chapter() -> None:
    result = parse_aggregate(aggregate({"1": volume("1", "0", "1")}))

    assert result == {Decimal(1): {Decimal(0), Decimal(1)}}


def test_volume_zero_is_a_volume_not_no_volume() -> None:
    result = parse_aggregate(aggregate({"0": volume("0", "1")}))

    assert result == {Decimal(0): {Decimal(1)}}


def test_a_volume_numbered_none_maps_to_no_volume() -> None:
    result = parse_aggregate(aggregate({"none": volume("none", "121", "122")}))

    assert result == {None: {Decimal(121), Decimal(122)}}


def test_a_chapter_with_no_number_is_skipped() -> None:
    result = parse_aggregate(aggregate({"none": volume("none", "none", "7")}))

    assert result == {None: {Decimal(7)}}


@pytest.mark.parametrize("chapter", ["", "abc", "NaN", "Infinity", "1e5", "-1", "1,5", "\u0661"])
def test_a_chapter_that_is_not_a_plain_number_is_skipped(chapter: str) -> None:
    result = parse_aggregate(aggregate({"1": volume("1", chapter, "2")}))

    assert result == {Decimal(1): {Decimal(2)}}


def test_the_volume_number_comes_from_its_field_not_its_key() -> None:
    result = parse_aggregate(aggregate({"first": volume("4", "30")}))

    assert result == {Decimal(4): {Decimal(30)}}


def test_the_chapter_number_comes_from_its_field_not_its_key() -> None:
    body = {"volume": "1", "count": 1, "chapters": {"a": chapter("12")}}

    assert parse_aggregate(aggregate({"1": body})) == {Decimal(1): {Decimal(12)}}


def test_two_volume_entries_with_the_same_number_are_merged() -> None:
    result = parse_aggregate(aggregate({"1": volume("1", "1"), "01": volume("01", "2")}))

    assert result == {Decimal(1): {Decimal(1), Decimal(2)}}


@pytest.mark.parametrize(
    "payload",
    [
        "not an object",
        {"result": "ok"},
        {"result": "ok", "volumes": "none"},
        {"result": "ok", "volumes": {"1": {"volume": "1", "chapters": "none"}}},
        {"result": "ok", "volumes": {"1": {"chapters": {}}}},
        {"result": "ok", "volumes": {"1": {"volume": "1", "chapters": {"1": {"id": "x"}}}}},
    ],
)
def test_an_unreadable_body_raises_a_validation_error(payload: object) -> None:
    with pytest.raises(ValidationError):
        parse_aggregate(payload)
