import re
from dataclasses import dataclass
from decimal import Decimal

from tomarr.parser.marker_scan import END_WORD, Kind, is_guessed, scan
from tomarr.parser.ranges import NumberList, parse_number_list
from tomarr.parser.release import ChapterRange, NumberRange, Unparseable


@dataclass(frozen=True)
class Markers:
    """What a name says about Volumes and Chapters.

    `title_end` is the index where the first marker begins, or `len(text)` when
    there is none, so `text[:title_end]` is everything before the numbers.
    `ambiguous` is true when a number was read by a guess (see `read_numbers`).
    """

    volumes: tuple[NumberRange, ...]
    chapters: tuple[ChapterRange, ...]
    title_end: int
    ambiguous: bool = False


# Only whitespace and a comma may sit between a Volume and the Chapter marker
# that states its chapters.
_PAIR_GAP = re.compile(r"[\s,]*")


def _numbers(text: str) -> NumberList | Unparseable:
    return parse_number_list(END_WORD.sub("", text.replace("+", ",")))


def _without_held_ranges(ranges: list[NumberRange]) -> tuple[NumberRange, ...]:
    """Drop each range another one holds (`16巻` after `第1-23巻`), keeping the order."""
    unique = list(dict.fromkeys(ranges))
    held: set[NumberRange] = set()
    widest_end: Decimal | None = None
    # By start, and the widest first among ranges that start together.
    by_start = sorted(sorted(unique, key=lambda r: r.end, reverse=True), key=lambda r: r.start)
    for numbers in by_start:
        if widest_end is not None and numbers.end <= widest_end:
            held.add(numbers)
        else:
            widest_end = numbers.end
    return tuple(numbers for numbers in unique if numbers not in held)


def read_numbers(text: str) -> Markers | Unparseable:
    """Find the Volume and Chapter markers in a name that has no tags left in it.

    A number with no marker (`One Piece 1190`) is not read. A Volume marker
    followed by a comma list gives its first item as the Volume and the unmarked
    items after it as Chapters (`v01-05,041-124`). A CJK suffix (`1, 2, 3巻`)
    makes the whole list before it one kind. A single Volume straight
    before a Chapter marker is that Chapter's `volume` and is not also reported
    as a Volume. A Volume inside another reported Volume range is not reported
    again. A number the normalizer refuses comes back as `Unparseable` with its
    reason.

    The result is `ambiguous` when a part letter or `part N` was read, when
    `parse_number_list` marks a list ambiguous, or when a marker is followed by
    a joiner it does not read (`c1 & 2`, `Vol. 1 to 5`) or a special word
    (`Ch. 10 Special`).
    """
    markers = scan(text)
    volumes: list[NumberRange] = []
    chapters: list[ChapterRange] = []
    paired_volume: Decimal | None = None
    ambiguous = any(is_guessed(text, marker) for marker in markers)
    for index, marker in enumerate(markers):
        if marker.kind is Kind.CHAPTER:
            numbers = _numbers(marker.first + marker.rest)
            if isinstance(numbers, Unparseable):
                return numbers
            ambiguous = ambiguous or numbers.ambiguous
            chapters += [ChapterRange(n.start, n.end, paired_volume) for n in numbers.ranges]
            paired_volume = None
            continue

        read_volumes = _numbers(marker.first)
        if isinstance(read_volumes, Unparseable):
            return read_volumes
        ambiguous = ambiguous or read_volumes.ambiguous
        if marker.rest:
            loose = _numbers(marker.rest.lstrip(" ,\uff0c+"))
            if isinstance(loose, Unparseable):
                return loose
            ambiguous = ambiguous or loose.ambiguous
            chapters += [ChapterRange(n.start, n.end) for n in loose.ranges]
        following = markers[index + 1] if index + 1 < len(markers) else None
        first = read_volumes.ranges[0]
        if (
            following
            and following.kind is Kind.CHAPTER
            and first.start == first.end
            and not marker.rest
            and _PAIR_GAP.fullmatch(text, marker.end, following.start)
        ):
            paired_volume = first.start
        else:
            volumes += read_volumes.ranges

    title_end = markers[0].start if markers else len(text)
    return Markers(
        _without_held_ranges(volumes), tuple(dict.fromkeys(chapters)), title_end, ambiguous
    )
