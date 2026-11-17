from collections.abc import Mapping
from decimal import ROUND_FLOOR, Decimal

from tomarr.parser.release import ParsedRelease

type ProviderChapters = Mapping[Decimal | None, frozenset[Decimal]]
"""The chapters a metadata provider lists for a Series, keyed by Volume.

`None` holds the chapters in no Volume, as in MangaDex's aggregate.
"""


def unlisted_decimals(
    parsed: ParsedRelease, provider_chapters: ProviderChapters
) -> tuple[Decimal, ...]:
    """Return the decimal chapter numbers of a Parsed release the provider does not list.

    Only chapter range endpoints with a fractional part are checked. A decimal is
    unlisted when it is missing from the reference chapters while the whole
    chapters on both sides of it are there. When a neighbor is missing the list is
    partial at that point, so the decimal is not judged.

    When the release names Volumes, the reference is the chapters listed under
    those Volumes only, so a named Volume the provider lists no chapters for
    judges nothing. Otherwise it is every listed chapter, including those in no
    Volume.
    """
    reference = _reference_chapters(parsed, provider_chapters)
    endpoints = {number for item in parsed.chapters for number in (item.start, item.end)}
    return tuple(sorted(number for number in endpoints if _is_unlisted(number, reference)))


def _reference_chapters(
    parsed: ParsedRelease, provider_chapters: ProviderChapters
) -> frozenset[Decimal]:
    paired = {item.volume for item in parsed.chapters if item.volume is not None}
    if not parsed.volumes and not paired:
        return frozenset[Decimal]().union(*provider_chapters.values())

    def is_named(volume: Decimal | None) -> bool:
        if volume is None:
            return False
        return volume in paired or any(span.start <= volume <= span.end for span in parsed.volumes)

    return frozenset[Decimal]().union(
        *(listed for volume, listed in provider_chapters.items() if is_named(volume))
    )


def _is_unlisted(number: Decimal, reference: frozenset[Decimal]) -> bool:
    # A whole number is its own floor, so it can never be both missing and listed. The
    # chapter above is built from an int, since `below + 1` rounds to the caller's precision.
    below = number.to_integral_value(rounding=ROUND_FLOOR)
    above = Decimal(int(below) + 1)
    return number not in reference and below in reference and above in reference
