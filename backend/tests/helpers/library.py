from dataclasses import dataclass

from tomarr.domain.chapter import Chapter
from tomarr.domain.edition import Edition
from tomarr.domain.series import Format, ReadingDirection, Series
from tomarr.domain.volume import Volume


@dataclass(frozen=True)
class Library:
    series: Series
    edition: Edition
    volume: Volume
    chapter: Chapter


def new_series(title: str = "Frieren") -> Series:
    return Series(title=title, format=Format.MANGA, reading_direction=ReadingDirection.RTL)
