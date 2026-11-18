import re
from collections import defaultdict
from decimal import Decimal

from pydantic import BaseModel

from tomarr.providers.base import VolumeChapters

_PLAIN_NUMBER = re.compile(r"[0-9]+(\.[0-9]+)?")


class _Chapter(BaseModel):
    chapter: str


class _Volume(BaseModel):
    volume: str
    chapters: dict[str, _Chapter]


class _AggregateResponse(BaseModel):
    volumes: dict[str, _Volume]


def parse_aggregate(payload: object) -> VolumeChapters:
    result: defaultdict[Decimal | None, set[Decimal]] = defaultdict(set)
    for volume in _AggregateResponse.model_validate(payload).volumes.values():
        # Read from the fields: the dict keys are not documented, and MangaDex spells "no number"
        # as the string "none" in both.
        chapters = result[_number(volume.volume)]
        chapters.update(
            number
            for chapter in volume.chapters.values()
            if (number := _number(chapter.chapter)) is not None
        )
    return {volume: frozenset(chapters) for volume, chapters in result.items()}


def _number(text: str) -> Decimal | None:
    return Decimal(text) if _PLAIN_NUMBER.fullmatch(text) else None
