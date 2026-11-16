import re
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, auto

from tomarr.parser.ranges import parse_number_list
from tomarr.parser.release import ChapterRange, NumberRange, Unparseable


@dataclass(frozen=True)
class Markers:
    """What a name says about Volumes and Chapters.

    `title_end` is the index where the first marker begins, or `len(text)` when
    there is none, so `text[:title_end]` is everything before the numbers.
    """

    volumes: tuple[NumberRange, ...]
    chapters: tuple[ChapterRange, ...]
    title_end: int


class _Kind(Enum):
    VOLUME = auto()
    CHAPTER = auto()


@dataclass(frozen=True)
class _Found:
    kind: _Kind
    start: int
    end: int
    first: str
    rest: str


_DIGITS = "0-9\uff10-\uff19"
# The trailing lookahead keeps a marker out of "v2026.03.26" and "3abc". A part
# letter ("10a") is left for the normalizer.
_NUMBER = rf"[{_DIGITS}]+(?:[.\uff0e][{_DIGITS}]+)?(?:[a-i](?![0-9a-z]))?(?![0-9a-z]|\.[{_DIGITS}])"
_RANGE_JOIN = r"\s*[-\uff0d]\s*"
_LIST_JOIN = r"\s*[,\uff0c+]\s*"

_VOLUME_WORD = r"(?:volumes?|vol\.?)\s*#?\s*|v#?"
_CHAPTER_WORD = r"(?:chapters?|ch\.?)\s*#?\s*|c#?"
_VOLUME_SUFFIX = "[巻卷册권]"
_CHAPTER_SUFFIX = "[話话화]"
# After the first number, "v000-v105" and "c000-c256" repeat the marker. Any
# number of ends is matched so that "1-2-3" reaches parse_number_list, which
# refuses it, instead of being cut to "1-2".
_END_WORD = re.compile(rf"(?:{_VOLUME_WORD}|{_CHAPTER_WORD})(?=[{_DIGITS}])", re.IGNORECASE)


def _marker(kind: _Kind, before: str, after: str, end_word: str) -> tuple[_Kind, re.Pattern[str]]:
    item = rf"{_NUMBER}(?:{_RANGE_JOIN}(?:{end_word})?{_NUMBER})*"
    pattern = rf"{before}(?P<first>{item})(?P<rest>(?:{_LIST_JOIN}{item})*){after}"
    return kind, re.compile(pattern, re.IGNORECASE)


# A suffix marker may only begin at the start of a number run. Without this,
# every digit of a long "1-1-1-..." chain is tried and fails at the end.
_RUN_START = rf"(?<![0-9a-z.{_DIGITS}])(?<![{_DIGITS}][-+,\uff0d\uff0c])"
_PATTERNS = (
    _marker(_Kind.VOLUME, rf"(?<![0-9a-z])(?:{_VOLUME_WORD})", "", _VOLUME_WORD),
    _marker(_Kind.CHAPTER, rf"(?<![0-9a-z])(?:{_CHAPTER_WORD})", "", _CHAPTER_WORD),
    _marker(_Kind.VOLUME, _RUN_START + "第?", _VOLUME_SUFFIX, "(?!)"),
    _marker(_Kind.CHAPTER, _RUN_START + "第?", _CHAPTER_SUFFIX, "(?!)"),
)
# Only whitespace and a comma may sit between a Volume and the Chapter marker
# that states its chapters.
_PAIR_GAP = re.compile(r"[\s,]*")


def _scan(text: str) -> list[_Found]:
    found = [
        _Found(kind, match.start(), match.end(), match["first"], match["rest"])
        for kind, pattern in _PATTERNS
        for match in pattern.finditer(text)
    ]
    found.sort(key=lambda item: item.start)
    kept: list[_Found] = []
    for item in found:
        if not kept or item.start >= kept[-1].end:
            kept.append(item)
    return kept


def _numbers(text: str) -> tuple[NumberRange, ...] | Unparseable:
    return parse_number_list(_END_WORD.sub("", text.replace("+", ",")))


def read_numbers(text: str) -> Markers | Unparseable:
    """Find the Volume and Chapter markers in a name that has no tags left in it.

    A number with no marker (`One Piece 1190`) is not read. A Volume marker
    followed by a comma list gives its first item as the Volume and the unmarked
    items after it as Chapters (`v01-05,041-124`). A single Volume straight
    before a Chapter marker is that Chapter's `volume` and is not also reported
    as a Volume. A number the normalizer refuses comes back as `Unparseable`
    with its reason.
    """
    markers = _scan(text)
    volumes: list[NumberRange] = []
    chapters: list[ChapterRange] = []
    paired_volume: Decimal | None = None
    for index, marker in enumerate(markers):
        if marker.kind is _Kind.CHAPTER:
            numbers = _numbers(marker.first + marker.rest)
            if isinstance(numbers, Unparseable):
                return numbers
            chapters += [ChapterRange(n.start, n.end, paired_volume) for n in numbers]
            paired_volume = None
            continue

        read_volumes = _numbers(marker.first)
        if isinstance(read_volumes, Unparseable):
            return read_volumes
        if marker.rest:
            loose = _numbers(marker.rest.lstrip(" ,\uff0c+"))
            if isinstance(loose, Unparseable):
                return loose
            chapters += [ChapterRange(n.start, n.end) for n in loose]
        following = markers[index + 1] if index + 1 < len(markers) else None
        single = read_volumes[0].start if read_volumes[0].start == read_volumes[0].end else None
        if (
            following
            and following.kind is _Kind.CHAPTER
            and single is not None
            and not marker.rest
            and _PAIR_GAP.fullmatch(text, marker.end, following.start)
        ):
            paired_volume = single
        else:
            volumes += read_volumes

    title_end = markers[0].start if markers else len(text)
    return Markers(tuple(dict.fromkeys(volumes)), tuple(dict.fromkeys(chapters)), title_end)
