import re
from dataclasses import dataclass, replace

from tomarr.parser.chapter_number import InvalidChapterNumber, normalize_chapter_number
from tomarr.parser.release import NumberRange, Unparseable, UnparseableReason

# Every dash and tilde a name joins a range with, for a regex character class.
# NFKC folds none of the dashes to "-", so each is listed.
RANGE_JOINERS = "\\-\u2010-\u2015\u2212~\uff0d\uff5e"
# The full-width comma and hyphen are split here too: the normalizer folds
# them to ASCII, so a full-width "10,12" would otherwise reach it as 10.12.
_LIST_SEPARATOR = re.compile(r"[,\uff0c]")
# A joiner splits a range only after a number, or a number with a part letter
# ("10a-12"). That leaves the hyphen in "one-shot" and a leading "-1" to the
# normalizer, which reads the first as chapter 1 and refuses the second.
_RANGE_SEPARATOR = re.compile(rf"(?:(?<=\d)|(?<=\d[a-iA-I]))\s*[{RANGE_JOINERS}]\s*")
_THOUSANDS = re.compile(r"(?<![\d.])([1-9]\d{0,2})[,\uff0c](\d{3})(?!\d)")
# "v01 - 2000" and "Vol 3 - 2021 edition" end on a year, not on Volume 2000.
_YEAR_FIRST, _YEAR_LAST = 1900, 2100
_BELOW_YEAR_RANGES = 100


@dataclass(frozen=True)
class NumberList:
    """The ranges one list holds, and whether reading them took a guess."""

    ranges: tuple[NumberRange, ...]
    ambiguous: bool = False


def parse_number_list(text: str) -> NumberList | Unparseable:
    """Read `10`, `10-12` and comma lists of them into ranges.

    Splitting happens here, before the normalizer sees anything, because the
    normalizer reads `10,12` as 10.12 and refuses `10-12`. A number the
    normalizer refuses comes back as `Unparseable` with its reason. A range
    that ends below its start, or has more than two ends, has no such reason.

    The reading is `ambiguous` when a comma may be a thousands separator
    (`1,100` is read as 1100; `1-20,181-240` cannot be, so it stays a list),
    when the list goes backwards (`10,5`), or when a range from under 100 ends
    on a year (`1 - 2000` is read as 1 alone).
    """
    if _THOUSANDS.search(text):
        joined = _read(_THOUSANDS.sub(r"\1\2", text))
        if isinstance(joined, NumberList):
            return replace(joined, ambiguous=True)
    return _read(text)


def _read(text: str) -> NumberList | Unparseable:
    ranges: list[NumberRange] = []
    ambiguous = False
    for piece in _LIST_SEPARATOR.split(text):
        ends = _RANGE_SEPARATOR.split(piece)
        if len(ends) > 2:
            return Unparseable(UnparseableReason.INVALID_NUMBER)
        try:
            numbers = [normalize_chapter_number(end) for end in ends]
        except InvalidChapterNumber as error:
            return Unparseable(UnparseableReason.INVALID_NUMBER, error.reason)
        start, end = numbers[0], numbers[-1]
        if end < start:
            return Unparseable(UnparseableReason.INVALID_NUMBER)
        if start < _BELOW_YEAR_RANGES and _YEAR_FIRST <= end <= _YEAR_LAST:
            end, ambiguous = start, True
        if ranges and start < ranges[-1].end:
            ambiguous = True
        ranges.append(NumberRange(start, end))
    return NumberList(tuple(ranges), ambiguous)
