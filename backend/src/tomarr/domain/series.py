from enum import StrEnum

from sqlalchemy.orm import Mapped, mapped_column

from tomarr.domain.base import Base
from tomarr.domain.columns import string_enum


class Format(StrEnum):
    MANGA = "manga"
    MANHWA = "manhwa"
    WEBTOON = "webtoon"


class ReadingDirection(StrEnum):
    RTL = "rtl"
    LTR = "ltr"
    VERTICAL = "vertical"


class Series(Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    format: Mapped[Format] = mapped_column(string_enum(Format))
    reading_direction: Mapped[ReadingDirection] = mapped_column(string_enum(ReadingDirection))
