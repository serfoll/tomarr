from datetime import date
from decimal import Decimal

import pytest

from tomarr.matching.thresholds import Thresholds
from tomarr.providers.base import DatePrecision, VolumeMetadata
from tomarr.providers.ndl.mapper import parse_volumes
from tomarr.providers.response import UNREADABLE

THRESHOLDS = Thresholds(high=95, medium=85)
SERIES = "葬送のフリーレン"

_RSS_OPEN = (
    '<rss xmlns:dc="http://purl.org/dc/elements/1.1/"'
    ' xmlns:openSearch="http://a9.com/-/spec/opensearchrss/1.0/"'
    ' xmlns:dcndl="http://ndl.go.jp/dcndl/terms/"'
    ' xmlns:dcterms="http://purl.org/dc/terms/"'
    ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="2.0">'
    "<channel><title>葬送のフリーレン 726 - 国立国会図書館サーチ OpenSearch</title>"
    "<openSearch:totalResults>2</openSearch:totalResults>"
)
_RSS_CLOSE = "</channel></rss>"


def item(
    title: str = SERIES,
    *,
    volume: str | None = "VOL.1",
    issued: str | None = "2020.8",
    isbns: tuple[str, ...] = ("978-4-09-850180-9",),
) -> str:
    parts = [f"<title>{title}</title>", f"<dc:title>{title}</dc:title>"]
    if volume is not None:
        parts.append(f"<dcndl:volume>{volume}</dcndl:volume>")
    parts.append("<dcndl:seriesTitle>少年サンデーコミックス</dcndl:seriesTitle>")
    if issued is not None:
        parts.append(f"<dcterms:issued>{issued}</dcterms:issued>")
    parts += [f'<dc:identifier xsi:type="dcndl:ISBN">{isbn}</dc:identifier>' for isbn in isbns]
    parts.append('<dc:identifier xsi:type="dcndl:NDLBibID">030560687</dc:identifier>')
    return f"<item>{''.join(parts)}</item>"


def feed(*items: str) -> bytes:
    return f"{_RSS_OPEN}{''.join(items)}{_RSS_CLOSE}".encode()


def read(
    *items: str,
    title: str = SERIES,
    aliases: tuple[str, ...] = (),
    thresholds: Thresholds = THRESHOLDS,
) -> list[VolumeMetadata]:
    return parse_volumes(feed(*items), title, aliases, thresholds)


def test_an_item_maps_to_a_volume() -> None:
    assert read(item()) == [
        VolumeMetadata(
            number=Decimal(1),
            isbn="9784098501809",
            release_date=date(2020, 8, 1),
            release_precision=DatePrecision.MONTH,
        )
    ]


@pytest.mark.parametrize(
    ("volume", "number"),
    [
        ("VOL.1", Decimal(1)),
        ("Vol. 10", Decimal(10)),
        ("Vol.10", Decimal(10)),
        ("Vol.1.5", Decimal("1.5")),
        ("Vol.0", Decimal(0)),
        ("VOL.99999", Decimal(99999)),
    ],
)
def test_the_volume_string_gives_the_number(volume: str, number: Decimal) -> None:
    assert [v.number for v in read(item(volume=volume))] == [number]


@pytest.mark.parametrize("volume", [None, "", "上", "VOL.100000", "VOL.1-2", "Vol. 3 part 1"])
def test_an_item_whose_volume_is_missing_or_not_one_number_is_dropped(volume: str | None) -> None:
    assert read(item(volume=volume)) == []


@pytest.mark.parametrize(
    "isbn",
    [
        "978-4-09-850180-9",
        "9784098501809",
        "978 4 09 850180 9",
    ],
)
def test_an_isbn_becomes_13_digits_without_hyphens(isbn: str) -> None:
    assert [v.isbn for v in read(item(isbns=(isbn,)))] == ["9784098501809"]


@pytest.mark.parametrize(
    "isbn",
    ["978-4-09-850180-8", "4098501806", "978409850180", "97840985018099", "", "abcdefghijklm"],
)
def test_an_item_whose_only_isbn_is_not_valid_is_dropped(isbn: str) -> None:
    assert read(item(isbns=(isbn,))) == []


@pytest.mark.parametrize(
    ("isbn", "isbn_13"),
    [
        ("4-09-850180-5", "9784098501809"),
        ("4098501805", "9784098501809"),
        # Real NDL identifiers for pre-2007 volumes.
        ("4-08-851688-5", "9784088516882"),
        ("493139681X", "9784931396814"),
    ],
)
def test_an_isbn_10_is_converted_to_isbn_13(isbn: str, isbn_13: str) -> None:
    assert [v.isbn for v in read(item(isbns=(isbn,)))] == [isbn_13]


@pytest.mark.parametrize("isbn", ["4098501806", "409850180Y", "4-09-850180-x", "40985018"])
def test_an_item_whose_only_isbn_is_an_invalid_isbn_10_is_dropped(isbn: str) -> None:
    assert read(item(isbns=(isbn,))) == []


def test_an_isbn_10_and_its_isbn_13_are_one_isbn() -> None:
    volumes = read(item(isbns=("4-09-850180-5", "978-4-09-850180-9")))

    assert [(v.isbn, v.other_isbns) for v in volumes] == [("9784098501809", ())]


def test_an_item_with_no_isbn_is_dropped() -> None:
    assert read(item(isbns=())) == []


def test_an_invalid_isbn_is_skipped_when_the_item_has_a_valid_one() -> None:
    volumes = read(item(isbns=("978-4-09-850180-8", "978-4-09-850180-9")))

    assert [(v.isbn, v.other_isbns) for v in volumes] == [("9784098501809", ())]


def test_an_identifier_that_is_not_an_isbn_is_not_read_as_one() -> None:
    body = feed(item(isbns=())).replace(b"030560687", b"9784098501809")

    assert parse_volumes(body, SERIES, (), THRESHOLDS) == []


def _with_isbn_type(xsi_type: str, declaration: str) -> bytes:
    body = feed(item()).decode()
    body = body.replace('xsi:type="dcndl:ISBN"', f'xsi:type="{xsi_type}"')
    return body.replace("<rss", f"<rss {declaration}", 1).encode()


def test_an_isbn_is_read_when_the_dcndl_namespace_has_another_prefix() -> None:
    body = _with_isbn_type("ndl:ISBN", 'xmlns:ndl="http://ndl.go.jp/dcndl/terms/"')

    assert [v.isbn for v in parse_volumes(body, SERIES, (), THRESHOLDS)] == ["9784098501809"]


@pytest.mark.parametrize(
    ("xsi_type", "declaration"),
    [
        ("ndl:ISBN", 'xmlns:ndl="http://example.com/other"'),
        ("unbound:ISBN", ""),
        ("ISBN", ""),
        ("dcndl:NDLBibID", ""),
    ],
)
def test_an_identifier_whose_type_is_not_the_dcndl_isbn_is_not_read(
    xsi_type: str, declaration: str
) -> None:
    body = _with_isbn_type(xsi_type, declaration)

    assert parse_volumes(body, SERIES, (), THRESHOLDS) == []


@pytest.mark.parametrize(
    ("issued", "date_read", "precision"),
    [
        ("2020.8", date(2020, 8, 1), DatePrecision.MONTH),
        ("2020.12", date(2020, 12, 1), DatePrecision.MONTH),
        ("2020", None, None),
        ("2020.13", None, None),
        ("2020.0", None, None),
        ("soon", None, None),
        (None, None, None),
    ],
)
def test_the_issued_date_has_month_precision_or_is_left_out(
    issued: str | None, date_read: date | None, precision: DatePrecision | None
) -> None:
    [volume] = read(item(issued=issued))

    assert (volume.release_date, volume.release_precision) == (date_read, precision)


def test_an_issued_year_of_zero_is_left_out_and_keeps_the_other_volumes() -> None:
    volumes = read(
        item(volume="VOL.1"),
        item(volume="VOL.2", issued="0000.5", isbns=("978-4-09-850181-6",)),
    )

    assert [(v.number, v.release_date, v.release_precision) for v in volumes] == [
        (Decimal(1), date(2020, 8, 1), DatePrecision.MONTH),
        (Decimal(2), None, None),
    ]


def test_a_volume_listed_under_two_isbns_is_one_volume_that_keeps_both() -> None:
    volumes = read(
        item(volume="VOL.10", isbns=("9784098517718",)),
        item(volume="Vol. 10", isbns=("978-4-09-943125-9",)),
    )

    assert [(v.number, v.isbn, v.other_isbns) for v in volumes] == [
        (Decimal(10), "9784098517718", ("9784099431259",))
    ]


def test_a_second_volume_listing_an_isbn_the_first_has_is_dropped() -> None:
    volumes = read(
        item(volume="VOL.1", isbns=("9784098501809",)),
        item(volume="VOL.2", isbns=("978-4-09-850180-9",)),
    )

    assert [(v.number, v.isbn, v.other_isbns) for v in volumes] == [
        (Decimal(1), "9784098501809", ())
    ]


def test_a_second_volume_keeps_its_own_isbns_and_loses_the_shared_one() -> None:
    volumes = read(
        item(volume="VOL.1", isbns=("9784098501809",)),
        item(volume="VOL.2", isbns=("9784098501809", "9784098501816")),
    )

    assert [(v.number, v.isbn, v.other_isbns) for v in volumes] == [
        (Decimal(1), "9784098501809", ()),
        (Decimal(2), "9784098501816", ()),
    ]


def test_the_first_volume_in_feed_order_keeps_a_shared_isbn() -> None:
    volumes = read(
        item(volume="VOL.2", isbns=("9784098501809",)),
        item(volume="VOL.1", isbns=("9784098501809",)),
    )

    assert [(v.number, v.isbn) for v in volumes] == [(Decimal(2), "9784098501809")]


def test_an_isbn_listed_twice_is_kept_once() -> None:
    volumes = read(
        item(volume="VOL.10", isbns=("9784098517718", "9784098517718")),
        item(volume="Vol. 10", isbns=("978-4-09-851771-8", "978-4-09-943125-9")),
    )

    assert [(v.isbn, v.other_isbns) for v in volumes] == [("9784098517718", ("9784099431259",))]


def test_a_merged_volume_takes_the_first_release_date_that_is_given() -> None:
    volumes = read(
        item(volume="VOL.10", issued=None, isbns=("9784098517718",)),
        item(volume="Vol. 10", issued="2023.3", isbns=("978-4-09-943125-9",)),
    )

    assert [(v.release_date, v.release_precision) for v in volumes] == [
        (date(2023, 3, 1), DatePrecision.MONTH)
    ]


def test_volumes_come_back_in_number_order() -> None:
    volumes = read(
        item(volume="Vol. 10", isbns=("978-4-09-943125-9",)),
        item(volume="VOL.2", isbns=("978-4-09-850181-6",)),
        item(volume="VOL.1"),
    )

    assert [v.number for v in volumes] == [Decimal(1), Decimal(2), Decimal(10)]


@pytest.mark.parametrize(
    "title",
    [
        "葬送のフリーレンアンソロジー : 異なる旅を楽しむ魔法",
        "葬送のフリーレン公式ファンブック",
        "〈葬送のフリーレン〉ぬり絵BOOK",
        "〈葬送のフリーレン〉画集",
    ],
)
def test_an_item_that_is_not_a_volume_of_the_series_is_dropped(title: str) -> None:
    assert read(item(title)) == []


def test_a_title_that_matches_an_alias_is_kept() -> None:
    volumes = read(item("Sousou no Frieren"), aliases=("Sousou no Frieren",))

    assert [v.number for v in volumes] == [Decimal(1)]


def test_the_thresholds_decide_how_close_a_title_must_be() -> None:
    near = item("Sousou no Frierem")

    assert read(near, title="Sousou no Frieren", thresholds=Thresholds(high=90, medium=90))
    assert not read(near, title="Sousou no Frieren", thresholds=Thresholds(high=100, medium=100))


def test_an_empty_feed_has_no_volumes() -> None:
    assert read() == []


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"not xml",
        b"<html><body>Bad gateway</body></html>",
        b"<rss version='2.0'><channel><item></rss>",
        # NDL's own answer when it limits concurrent requests.
        b'<?xml version="1.0" encoding="UTF-8"?><error><code>429</code>'
        b"<message>Too Many Requests</message></error>",
    ],
)
def test_a_body_that_is_not_an_rss_feed_is_unreadable(body: bytes) -> None:
    with pytest.raises(UNREADABLE):
        parse_volumes(body, SERIES, (), THRESHOLDS)


@pytest.mark.parametrize(
    "prolog",
    [
        "<!DOCTYPE rss>",
        '<!DOCTYPE rss SYSTEM "http://127.0.0.1:9/rss.dtd">',
        '<!DOCTYPE rss [<!ENTITY volume "VOL.1">]>',
        '<!DOCTYPE rss [<!ENTITY volume SYSTEM "file:///etc/hostname">]>',
    ],
)
def test_a_body_with_a_doctype_is_unreadable(prolog: str) -> None:
    body = feed(item()).decode().replace("<rss", f"{prolog}<rss", 1).encode()

    with pytest.raises(UNREADABLE):
        parse_volumes(body, SERIES, (), THRESHOLDS)


def test_an_entity_with_no_doctype_is_unreadable() -> None:
    with pytest.raises(UNREADABLE):
        parse_volumes(feed(item(volume="&volume;")), SERIES, (), THRESHOLDS)


def test_the_predefined_entities_are_still_read() -> None:
    volumes = read(item("Tom &amp; Jerry", isbns=("9784098501809",)), title="Tom & Jerry")

    assert [v.number for v in volumes] == [Decimal(1)]
