from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field

from tomarr.parser.chapter_number import INTEGER_DIGITS, normalize_chapter_number

# Strict, so "12", true and 12.0 are a wrong type and not a chapter. The bounds sit here so any
# number the normalizer would refuse is a validation error too.
_LatestChapter = Annotated[int, Field(strict=True, ge=0, le=10**INTEGER_DIGITS - 1)]


class _SeriesResponse(BaseModel):
    latest_chapter: _LatestChapter | None = None


def parse_series(payload: object) -> Decimal | None:
    latest_chapter = _SeriesResponse.model_validate(payload).latest_chapter
    return None if latest_chapter is None else normalize_chapter_number(repr(latest_chapter))
