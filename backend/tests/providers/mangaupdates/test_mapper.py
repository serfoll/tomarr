from decimal import Decimal

import pytest
from pydantic import ValidationError

from tomarr.providers.mangaupdates.mapper import parse_series


def test_a_whole_latest_chapter_maps_to_a_decimal() -> None:
    assert parse_series({"series_id": 55099335, "latest_chapter": 227}) == Decimal(227)


def test_a_latest_chapter_of_zero_maps_to_zero() -> None:
    assert parse_series({"latest_chapter": 0}) == Decimal(0)


@pytest.mark.parametrize("body", [{}, {"latest_chapter": None}])
def test_a_missing_or_null_latest_chapter_maps_to_none(body: dict[str, object]) -> None:
    assert parse_series(body) is None


def test_unknown_fields_are_ignored() -> None:
    body = {"latest_chapter": 12, "title": "Dandadan", "rating": {"average": 8.4}}

    assert parse_series(body) == Decimal(12)


@pytest.mark.parametrize("latest_chapter", ["12", True, 12.0, 12.5, [12], {"n": 12}, -3])
def test_a_latest_chapter_that_is_not_a_non_negative_integer_raises_a_validation_error(
    latest_chapter: object,
) -> None:
    with pytest.raises(ValidationError):
        parse_series({"latest_chapter": latest_chapter})


@pytest.mark.parametrize("payload", [[], "series", 12, None])
def test_a_body_that_is_not_an_object_raises_a_validation_error(payload: object) -> None:
    with pytest.raises(ValidationError):
        parse_series(payload)


def test_a_latest_chapter_too_large_for_a_chapter_number_raises_a_value_error() -> None:
    with pytest.raises(ValueError, match="too_large"):
        parse_series({"latest_chapter": 100000})
