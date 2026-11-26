import re
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal

from lxml import etree

# The stubs name no public type for an element.
from lxml.etree import _Element as Element  # pyright: ignore[reportPrivateUsage]

from tomarr.matching.matcher import match_title
from tomarr.matching.thresholds import Thresholds
from tomarr.parser.markers import read_numbers
from tomarr.parser.release import Unparseable
from tomarr.providers.base import DatePrecision, VolumeMetadata

_NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcndl": "http://ndl.go.jp/dcndl/terms/",
    "dcterms": "http://purl.org/dc/terms/",
}
_XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"

# The feed is a third party's, so the parser reads no DTD, expands no entity and opens no URL.
# A DOCTYPE is refused outright, since a real feed has none.
_PARSER = etree.XMLParser(
    resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False
)

_ISSUED = re.compile(r"([0-9]{4})\.([0-9]{1,2})")
_ISBN_SEPARATORS = re.compile(r"[\s-]")


def parse_volumes(
    body: bytes, title: str, aliases: Sequence[str], thresholds: Thresholds
) -> list[VolumeMetadata]:
    """Read the Volumes of one Series out of an OpenSearch feed, in number order.

    An item is a Volume of the Series when its title matches the Series title or one of its
    Aliases, it has a single Volume number and it has at least one valid ISBN. Anything else is
    dropped. An ISBN is valid when its check digit is, and an ISBN-10 is returned as its ISBN-13.
    The same Volume listed under several ISBNs comes back once, with the first ISBN in `isbn` and
    the others in `other_isbns`.

    An ISBN belongs to one Volume. When NDL lists it on two Volume numbers, the first Volume in
    feed order keeps it and a later one loses it from `isbn` and `other_isbns`, and is dropped
    when it has no ISBN left.

    Raises ValueError when the body is not an RSS feed, which includes a DOCTYPE.
    """
    root = _parse(body)
    merged: dict[Decimal, VolumeMetadata] = {}
    owner: dict[str, Decimal] = {}
    for element in root.iterfind("channel/item"):
        volume = _read_item(element, title, aliases, thresholds)
        if volume is None:
            continue
        isbns = [
            isbn
            for isbn in (volume.isbn, *volume.other_isbns)
            if owner.setdefault(isbn, volume.number) == volume.number
        ]
        if not isbns:
            continue
        volume = replace(volume, isbn=isbns[0], other_isbns=tuple(isbns[1:]))
        known = merged.get(volume.number)
        merged[volume.number] = volume if known is None else _merge(known, volume)
    return [merged[number] for number in sorted(merged)]


def _parse(body: bytes) -> Element:
    try:
        root = etree.fromstring(body, _PARSER)
    except etree.XMLSyntaxError:
        raise ValueError("The body is not XML.") from None
    if root.getroottree().docinfo.doctype:
        raise ValueError("The feed has a DOCTYPE.")
    if root.tag != "rss":
        raise ValueError("The body is not an RSS feed.")
    return root


def _read_item(
    element: Element, title: str, aliases: Sequence[str], thresholds: Thresholds
) -> VolumeMetadata | None:
    item_title = element.findtext("title", default="")
    if match_title(item_title, title, aliases, thresholds).confidence is None:
        return None
    number = _read_volume_number(element.findtext("dcndl:volume", default="", namespaces=_NS))
    isbns = _read_isbns(element)
    if number is None or not isbns:
        return None
    release_date, precision = _read_issued(element.findtext("dcterms:issued", namespaces=_NS))
    return VolumeMetadata(
        number=number,
        isbn=isbns[0],
        other_isbns=isbns[1:],
        release_date=release_date,
        release_precision=precision,
    )


def _merge(first: VolumeMetadata, second: VolumeMetadata) -> VolumeMetadata:
    other_isbns = tuple(
        dict.fromkeys(isbn for isbn in (*first.other_isbns, second.isbn, *second.other_isbns))
    )
    keep_second_date = first.release_date is None
    return VolumeMetadata(
        number=first.number,
        isbn=first.isbn,
        other_isbns=tuple(isbn for isbn in other_isbns if isbn != first.isbn),
        release_date=second.release_date if keep_second_date else first.release_date,
        release_precision=second.release_precision if keep_second_date else first.release_precision,
    )


def _read_volume_number(text: str) -> Decimal | None:
    # NDL writes `VOL.1`, `Vol. 10` and `Vol.10`, which the release parser's Volume marker reads.
    # A range or a part letter is not one Volume's number.
    markers = read_numbers(text)
    if isinstance(markers, Unparseable) or markers.ambiguous or markers.chapters:
        return None
    match markers.volumes:
        case (numbers,) if numbers.start == numbers.end:
            return numbers.start
        case _:
            return None


def _read_isbns(element: Element) -> tuple[str, ...]:
    found = (
        _read_isbn(identifier.text or "")
        for identifier in element.iterfind("dc:identifier", _NS)
        if _is_isbn_type(identifier)
    )
    return tuple(dict.fromkeys(isbn for isbn in found if isbn is not None))


def _is_isbn_type(identifier: Element) -> bool:
    # The prefix is the feed's choice, so xsi:type is read as a QName against the element's scope.
    prefix, colon, local = identifier.get(_XSI_TYPE, "").partition(":")
    return bool(colon) and local == "ISBN" and identifier.nsmap.get(prefix) == _NS["dcndl"]


def _read_isbn(text: str) -> str | None:
    digits = _ISBN_SEPARATORS.sub("", text)
    if re.fullmatch(r"[0-9]{13}", digits):
        return digits if _check_digit_13(digits[:12]) == digits[12] else None
    # Volumes from before 2007 carry only an ISBN-10, which is read as its ISBN-13.
    if re.fullmatch(r"[0-9]{9}[0-9X]", digits):
        weighted = sum(
            (10 - place) * (10 if char == "X" else int(char)) for place, char in enumerate(digits)
        )
        if weighted % 11 != 0:
            return None
        converted = f"978{digits[:9]}"
        return converted + _check_digit_13(converted)
    return None


def _check_digit_13(first_twelve: str) -> str:
    total = sum(int(char) * (3 if place % 2 else 1) for place, char in enumerate(first_twelve))
    return str((10 - total % 10) % 10)


def _read_issued(text: str | None) -> tuple[date | None, DatePrecision | None]:
    match = _ISSUED.fullmatch(text.strip()) if text else None
    if match is None:
        return None, None
    year, month = int(match[1]), int(match[2])
    if year < 1 or not 1 <= month <= 12:
        return None, None
    return date(year, month, 1), DatePrecision.MONTH
