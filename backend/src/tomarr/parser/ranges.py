import re

from tomarr.parser.chapter_number import InvalidChapterNumber, normalize_chapter_number
from tomarr.parser.release import NumberRange, Unparseable, UnparseableReason

# The full-width comma and hyphen are split here too: the normalizer folds
# them to ASCII, so a full-width "10,12" would otherwise reach it as 10.12.
_LIST_SEPARATOR = re.compile(r"[,\uff0c]")
# A hyphen splits a range only after a number, or a number with a part letter
# ("10a-12"). That leaves the hyphen in "one-shot" and a leading "-1" to the
# normalizer, which reads the first as chapter 1 and refuses the second.
_RANGE_SEPARATOR = re.compile(r"(?:(?<=\d)|(?<=\d[a-iA-I]))\s*[-\uff0d]\s*")


def parse_number_list(text: str) -> tuple[NumberRange, ...] | Unparseable:
    """Read `10`, `10-12` and comma lists of them into ranges.

    Splitting happens here, before the normalizer sees anything, because the
    normalizer reads `10,12` as 10.12 and refuses `10-12`. A number the
    normalizer refuses comes back as `Unparseable` with its reason. A range
    that ends below its start, or has more than two ends, has no such reason.
    """
    ranges: list[NumberRange] = []
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
        ranges.append(NumberRange(start, end))
    return tuple(ranges)
