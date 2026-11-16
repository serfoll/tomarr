from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from tomarr.parser.chapter_number import ChapterNumberReason


class UnparseableReason(StrEnum):
    VIDEO = "video"
    AUDIOBOOK = "audiobook"
    NO_TITLE = "no_title"
    INVALID_NUMBER = "invalid_number"


class ReleaseWarning(StrEnum):
    MIXED_PACK = "mixed_pack"
    NO_NUMBERS = "no_numbers"


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
