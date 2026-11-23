import logging
import re
from collections import defaultdict
from decimal import Decimal

from pydantic import BaseModel

from tomarr.providers.base import VolumeChapters

logger = logging.getLogger(__name__)

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
    skipped_volumes = skipped_chapters = 0
    for volume in _AggregateResponse.model_validate(payload).volumes.values():
        # Read from the fields: the dict keys are not documented, and MangaDex spells "no number"
        # as the string "none" in both.
        if _is_none(volume.volume):
            chapters = result[None]
        elif (volume_number := _number(volume.volume)) is not None:
            chapters = result[volume_number]
        else:
            skipped_volumes += 1
            continue
        for chapter in volume.chapters.values():
            if (number := _number(chapter.chapter)) is not None:
                chapters.add(number)
            elif not _is_none(chapter.chapter):
                skipped_chapters += 1
    if skipped_volumes or skipped_chapters:
        # Counts only: the numbers are the provider's text.
        logger.warning(
            "MangaDex listed numbers Tomarr cannot read. Skipped %d volume(s) and %d chapter(s).",
            skipped_volumes,
            skipped_chapters,
        )
    return {volume: frozenset(chapters) for volume, chapters in result.items()}


def _is_none(text: str) -> bool:
    return text.lower() == "none"


def _number(text: str) -> Decimal | None:
    return Decimal(text) if _PLAIN_NUMBER.fullmatch(text) else None
