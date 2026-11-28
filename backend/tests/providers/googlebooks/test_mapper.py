from datetime import date

import pytest

from tomarr.providers.base import DatePrecision, VolumeDetails
from tomarr.providers.googlebooks.mapper import parse_volume_details
from tomarr.providers.response import UNREADABLE

ONE_PIECE_115 = "9784088851303"
FRIEREN_1 = "9784098501809"
MASHIRO_3 = "9784088851488"


def volume_info(isbn: str = ONE_PIECE_115, **fields: object) -> dict[str, object]:
    return {
        "title": "ONE PIECE 115",
        "industryIdentifiers": [
            {"type": "ISBN_10", "identifier": "4088851307"},
            {"type": "ISBN_13", "identifier": isbn},
        ],
        "language": "ja",
        **fields,
    }


def body(*infos: dict[str, object]) -> dict[str, object]:
    return {
        "kind": "books#volumes",
        "totalItems": len(infos),
        "items": [
            {"kind": "books#volume", "id": f"id{n}", "volumeInfo": i} for n, i in enumerate(infos)
        ],
    }


def test_a_full_record_gives_synopsis_https_cover_and_day_precision_date() -> None:
    info = volume_info(
        description="The Straw Hats reach the island.",
        publishedDate="2026-03-04",
        imageLinks={
            "smallThumbnail": "http://books.google.com/books/content?id=a&zoom=5",
            "thumbnail": "http://books.google.com/books/content?id=a&zoom=1",
        },
    )

    assert parse_volume_details(body(info), ONE_PIECE_115) == VolumeDetails(
        synopsis="The Straw Hats reach the island.",
        cover_url="https://books.google.com/books/content?id=a&zoom=1",
        release_date=date(2026, 3, 4),
        release_precision=DatePrecision.DAY,
    )


def test_a_year_and_month_gives_month_precision_on_the_first() -> None:
    info = volume_info(FRIEREN_1, publishedDate="2020-08")

    details = parse_volume_details(body(info), FRIEREN_1)

    assert details is not None
    assert (details.release_date, details.release_precision) == (
        date(2020, 8, 1),
        DatePrecision.MONTH,
    )


@pytest.mark.parametrize("published", ["2020", "soon", "2020-13", "2020-02-31", "0000-01-01", ""])
def test_a_date_that_is_not_a_day_or_a_month_gives_no_date_and_keeps_the_rest(
    published: str,
) -> None:
    info = volume_info(FRIEREN_1, publishedDate=published, description="An elf mage.")

    assert parse_volume_details(body(info), FRIEREN_1) == VolumeDetails(synopsis="An elf mage.")


def test_a_record_with_no_published_date_gives_no_date() -> None:
    details = parse_volume_details(body(volume_info(MASHIRO_3)), MASHIRO_3)

    assert details == VolumeDetails()


@pytest.mark.parametrize("description", ["", "   \n", None])
def test_an_empty_or_missing_description_gives_no_synopsis(description: str | None) -> None:
    info = volume_info(MASHIRO_3, description=description, publishedDate="2026-01-01")

    details = parse_volume_details(body(info), MASHIRO_3)

    assert details is not None
    assert details.synopsis is None


def test_a_record_with_no_description_key_gives_no_synopsis() -> None:
    details = parse_volume_details(body(volume_info(MASHIRO_3)), MASHIRO_3)

    assert details is not None
    assert details.synopsis is None


def test_the_thumbnail_is_preferred_over_the_small_one() -> None:
    links = {"smallThumbnail": "https://x/small", "thumbnail": "https://x/big"}

    details = parse_volume_details(body(volume_info(imageLinks=links)), ONE_PIECE_115)

    assert details is not None
    assert details.cover_url == "https://x/big"


def test_the_small_thumbnail_is_the_fallback() -> None:
    links = {"smallThumbnail": "https://x/small"}

    details = parse_volume_details(body(volume_info(imageLinks=links)), ONE_PIECE_115)

    assert details is not None
    assert details.cover_url == "https://x/small"


def test_no_image_links_gives_no_cover() -> None:
    details = parse_volume_details(body(volume_info()), ONE_PIECE_115)

    assert details is not None
    assert details.cover_url is None


def test_an_item_for_another_isbn_is_ignored() -> None:
    assert parse_volume_details(body(volume_info(FRIEREN_1)), ONE_PIECE_115) is None


def test_the_item_whose_isbn_matches_wins_among_several() -> None:
    other = volume_info(FRIEREN_1, description="wrong")
    wanted = volume_info(ONE_PIECE_115, description="right")

    details = parse_volume_details(body(other, wanted), ONE_PIECE_115)

    assert details == VolumeDetails(synopsis="right")


def test_an_isbn_10_alone_does_not_match() -> None:
    info: dict[str, object] = {
        "industryIdentifiers": [{"type": "ISBN_10", "identifier": ONE_PIECE_115}]
    }

    assert parse_volume_details(body(info), ONE_PIECE_115) is None


@pytest.mark.parametrize(
    "response",
    [
        {"kind": "books#volumes", "totalItems": 0},
        {"totalItems": 0, "items": []},
        {"items": [{}]},
    ],
)
def test_no_items_gives_none(response: object) -> None:
    assert parse_volume_details(response, ONE_PIECE_115) is None


@pytest.mark.parametrize(
    "response",
    [
        [],
        "nope",
        None,
        {"items": {}},
        {"items": "x"},
        {"items": [{"volumeInfo": []}]},
        {"items": [{"volumeInfo": "x"}]},
        {"items": [{"volumeInfo": {"industryIdentifiers": {}}}]},
        {"items": [{"volumeInfo": {"description": 5, "industryIdentifiers": []}}]},
    ],
)
def test_a_body_of_the_wrong_shape_is_unreadable(response: object) -> None:
    with pytest.raises(UNREADABLE):
        parse_volume_details(response, ONE_PIECE_115)
