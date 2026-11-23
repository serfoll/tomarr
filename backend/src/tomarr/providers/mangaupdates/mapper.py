from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field

from tomarr.parser.chapter_number import normalize_chapter_number


class _SeriesResponse(BaseModel):
    # Strict, so "12", true and 12.0 are a wrong type and not a chapter. A negative number is
    # refused here, where the error is logged as a body Tomarr does not recognize.
    latest_chapter: Annotated[int, Field(strict=True, ge=0)] | None = None


def parse_series(payload: object) -> Decimal | None:
    latest_chapter = _SeriesResponse.model_validate(payload).latest_chapter
    return None if latest_chapter is None else normalize_chapter_number(repr(latest_chapter))
