"""The marker grammar: where Volume and Chapter markers sit in a name's text."""

import re
from dataclasses import dataclass
from enum import Enum, auto

from tomarr.parser.ranges import RANGE_JOINERS


class Kind(Enum):
    VOLUME = auto()
    CHAPTER = auto()


@dataclass(frozen=True)
class Found:
    """One marker: `first` is its first list item, `rest` the items after it."""

    kind: Kind
    start: int
    end: int
    first: str
    rest: str


_DIGITS = "0-9\uff10-\uff19"
# Whitespace is bounded so a failed attempt costs a fixed amount at any start
# position, which keeps a whole scan linear in the name length.
_SPACE = r"\s{0,3}"
# The trailing lookahead keeps a marker out of "v2026.03.26" and "3abc". A part
# letter ("10a") or "part 2" is left for the normalizer.
_PART = rf"[a-i](?![0-9a-z])|{_SPACE}part{_SPACE}[1-9]"
_NUMBER = rf"[{_DIGITS}]+(?:[.\uff0e][{_DIGITS}]+)?(?:{_PART})?(?![0-9a-z]|\.[{_DIGITS}])"
_RANGE_JOIN = rf"{_SPACE}[{RANGE_JOINERS}]{_SPACE}"
_LIST_JOIN = rf"{_SPACE}[,\uff0c+]{_SPACE}"

_VOLUME_WORD = rf"(?:volumes?|vol\.?){_SPACE}#?{_SPACE}|v#?"
_CHAPTER_WORD = rf"(?:chapters?|ch\.?){_SPACE}#?{_SPACE}|c#?"
_VOLUME_SUFFIXES = "巻卷册권"
_CHAPTER_SUFFIXES = "話话화"
# After the first number, "v000-v105" and "c000-c256" repeat the marker. Any
# number of ends is matched so that "1-2-3-4" reaches parse_number_list, which
# refuses it, instead of being cut short and losing the tail.
END_WORD = re.compile(rf"(?:{_VOLUME_WORD}|{_CHAPTER_WORD})(?=[{_DIGITS}])", re.IGNORECASE)


def _marker(
    kind: Kind, before: str, suffixes: str, end_word: str
) -> tuple[Kind, re.Pattern[str], str]:
    # A CJK range may repeat its suffix before the joiner ("3話-5話").
    between = f"[{suffixes}]?" if suffixes else ""
    item = rf"{_NUMBER}(?:{between}{_RANGE_JOIN}(?:{end_word})?{_NUMBER})*"
    pattern = rf"{before}(?P<first>{item})(?P<rest>(?:{_LIST_JOIN}{item})*)"
    return kind, re.compile(pattern, re.IGNORECASE), suffixes


# A suffix marker may only begin at the start of a number run, so a long
# "1-1-1-..." chain is tried once and not from every digit.
_RUN_START = rf"(?<![0-9a-z.{_DIGITS}])(?<![{_DIGITS}][{RANGE_JOINERS}+,\uff0c])"
# The suffix is checked after the match, not in the pattern: a list followed by
# something else is consumed whole instead of retried from each of its numbers.
# CJK ranges never repeat a marker after the hyphen, so their end-marker slot is
# "(?!)", a pattern that cannot match.
_PATTERNS = (
    _marker(Kind.VOLUME, rf"(?<![0-9a-z])(?:{_VOLUME_WORD})", "", _VOLUME_WORD),
    _marker(Kind.CHAPTER, rf"(?<![0-9a-z])(?:{_CHAPTER_WORD})", "", _CHAPTER_WORD),
    _marker(Kind.VOLUME, _RUN_START + "第?", _VOLUME_SUFFIXES, "(?!)"),
    _marker(Kind.CHAPTER, _RUN_START + "第?", _CHAPTER_SUFFIXES, "(?!)"),
)
# "V1 Batch" numbers an upload batch, not a Volume.
_BATCH = re.compile(r"\s{0,3}batch\b", re.IGNORECASE)
# The normalizer reads "10a" and "10 part 1" as 10.1, the same as a real 10.1.
_GUESSED_PART = re.compile(rf"[{_DIGITS}][a-i]|part", re.IGNORECASE)
# A joiner the marker does not read ("c1 & 2") or a special word ("Ch. 10
# Special") leaves part of what the name numbers unread.
_UNREAD_AFTER = re.compile(
    rf"{_SPACE}(?:(?:&|and|to|/|\+){_SPACE}[{_DIGITS}]"
    r"|(?:specials?|extras?|omake|bonus|one[\s-]?shots?)\b)",
    re.IGNORECASE,
)


def scan(text: str) -> list[Found]:
    """Every marker in `text`, in order, none overlapping another."""
    found: list[Found] = []
    for kind, pattern, suffixes in _PATTERNS:
        for match in pattern.finditer(text):
            end = match.end()
            first, rest = match["first"], match["rest"]
            if kind is Kind.VOLUME and _BATCH.match(text, end):
                continue
            if suffixes:
                if end == len(text) or text[end] not in suffixes:
                    continue
                # The suffix names the kind of every number before it.
                end, first, rest = end + 1, re.sub(f"[{suffixes}]", "", first + rest), ""
            found.append(Found(kind, match.start(), end, first, rest))
    found.sort(key=lambda item: item.start)
    kept: list[Found] = []
    for item in found:
        if not kept or item.start >= kept[-1].end:
            kept.append(item)
    return kept


def is_guessed(text: str, marker: Found) -> bool:
    """Whether reading this marker of `text` takes a guess about its numbers."""
    return bool(
        _UNREAD_AFTER.match(text, marker.end) or _GUESSED_PART.search(marker.first + marker.rest)
    )
