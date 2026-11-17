from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from tomarr.parser.chapter_number import ChapterNumberReason


class UnparseableReason(StrEnum):
    VIDEO = "video"
    AUDIOBOOK = "audiobook"
    GAME = "game"
    NO_TITLE = "no_title"
    INVALID_NUMBER = "invalid_number"
    TOO_LONG = "too_long"


class ReleaseWarning(StrEnum):
    MIXED_PACK = "mixed_pack"
    NO_NUMBERS = "no_numbers"
    AMBIGUOUS_NUMBER = "ambiguous_number"


class Source(StrEnum):
    DIGITAL = "digital"
    SCAN = "scan"
    UNKNOWN = "unknown"


class EditionHint(StrEnum):
    COLORED = "colored"
    WEBTOON = "webtoon"


class FileFormat(StrEnum):
    CBZ = "cbz"
    CBR = "cbr"
    ZIP = "zip"
    RAR = "rar"
    PDF = "pdf"
    EPUB = "epub"


@dataclass(frozen=True)
class NumberRange:
    start: Decimal
    end: Decimal


@dataclass(frozen=True)
class ChapterRange:
    start: Decimal
    end: Decimal
    volume: Decimal | None = None


@dataclass(frozen=True)
class ParsedRelease:
    """What one release name says, read without matching it to a Series.

    `volumes` holds only the Volumes reported on their own. A Volume that
    states its chapters (`Vol. 3 Ch. 12-20`) is the `volume` of those chapter
    ranges and is not repeated in `volumes`, so every Volume a release holds is
    `volumes` together with each `chapters[].volume`.

    `clean` is false when any warning is set: `mixed_pack` (Volume ranges beside
    chapters that belong to no Volume), `no_numbers` (no marker was read) or
    `ambiguous_number` (a number was read by a guess: a part letter or `part N`,
    a thousands comma, a list that goes backwards, a range that ends on a year,
    a joiner or special word after a marker that is left unread, or a `(v2)`
    revision tag).
    """

    title: str
    volumes: tuple[NumberRange, ...] = ()
    chapters: tuple[ChapterRange, ...] = ()
    group: str | None = None
    source: Source = Source.UNKNOWN
    language: str | None = None
    hints: frozenset[EditionHint] = field(default_factory=frozenset[EditionHint])
    file_format: FileFormat | None = None
    warnings: frozenset[ReleaseWarning] = field(default_factory=frozenset[ReleaseWarning])

    @property
    def clean(self) -> bool:
        return not self.warnings


@dataclass(frozen=True)
class Unparseable:
    reason: UnparseableReason
    number_reason: ChapterNumberReason | None = None


ParseOutcome = ParsedRelease | Unparseable
