from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from tomarr.matching.chapters import ProviderChapters, unlisted_decimals
from tomarr.matching.confidence import Confidence, lower
from tomarr.matching.matcher import TitleMatchReason, match_title
from tomarr.matching.thresholds import Thresholds
from tomarr.parser.release import ParsedRelease


class Lowering(StrEnum):
    UNCLEAN_PARSE = "unclean_parse"
    UNLISTED_DECIMAL = "unlisted_decimal"


@dataclass(frozen=True)
class ReleaseMatch:
    """How well a Parsed release fits a Series, and what lowered its Confidence.

    `confidence` is None when the title was refused, and then nothing was lowered.
    `unlisted_chapters` holds the decimal chapters the provider does not list.
    """

    confidence: Confidence | None
    score: float
    matched: str | None
    reason: TitleMatchReason | None
    lowered_by: tuple[Lowering, ...]
    unlisted_chapters: tuple[Decimal, ...]


def assess_release(
    parsed: ParsedRelease,
    title: str,
    aliases: Sequence[str],
    thresholds: Thresholds,
    provider_chapters: ProviderChapters,
) -> ReleaseMatch:
    """Match a Parsed release to a Series, lowering the Confidence once per cause.

    An unclean parse is one cause however many warnings it carries, and an unlisted
    decimal is another. `low` is the floor.
    """
    title_match = match_title(parsed.title, title, aliases, thresholds)
    if title_match.confidence is None:
        return ReleaseMatch(
            None, title_match.score, title_match.matched, title_match.reason, (), ()
        )

    confidence = title_match.confidence
    lowered_by: list[Lowering] = []
    if not parsed.clean:
        confidence = lower(confidence)
        lowered_by.append(Lowering.UNCLEAN_PARSE)
    unlisted = unlisted_decimals(parsed, provider_chapters)
    if unlisted:
        confidence = lower(confidence)
        lowered_by.append(Lowering.UNLISTED_DECIMAL)

    return ReleaseMatch(
        confidence, title_match.score, title_match.matched, None, tuple(lowered_by), unlisted
    )
