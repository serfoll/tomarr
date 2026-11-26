from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

from tomarr.domain.external_id import Provider
from tomarr.domain.series import Format
from tomarr.matching.thresholds import Thresholds


@dataclass(frozen=True)
class SeriesCandidate:
    """A series as one Provider describes it, before it is merged into a Series. `external_ids`
    holds the same work's IDs at other Providers. `status` is the Provider's own word for it, since
    Providers do not share a vocabulary."""

    provider: Provider
    provider_id: str
    title: str
    aliases: tuple[str, ...]
    format: Format | None
    status: str | None
    total_volumes: Decimal | None
    total_chapters: Decimal | None
    external_ids: Mapping[Provider, str]
    cover_url: str | None = None


@dataclass(frozen=True)
class CharacterName:
    """One character's names as a Provider gives them."""

    full: str
    native: str | None
    alternatives: tuple[str, ...]


class DatePrecision(StrEnum):
    """How much of a release date the Provider gave. The unstated part of a `date` is its first."""

    MONTH = "month"
    DAY = "day"


@dataclass(frozen=True)
class VolumeMetadata:
    """One Volume as a Provider describes it. `other_isbns` holds the ISBNs the Provider lists
    for the same Volume besides `isbn`, since a reprint or a second binding gets its own."""

    number: Decimal
    isbn: str
    title: str
    other_isbns: tuple[str, ...] = ()
    release_date: date | None = None
    release_precision: DatePrecision | None = None
    cover_url: str | None = None
    synopsis: str | None = None
    upcoming: bool = False


type VolumeChapters = Mapping[Decimal | None, frozenset[Decimal]]
"""The chapters a Provider lists for a Series, keyed by Volume number. `None` holds the chapters
in no Volume. A Volume the Provider lists with no chapters maps to an empty set, and one it does
not list at all is absent. The same chapter number can be listed under several Volumes, or under a
Volume and `None`; a caller that stores one Chapter per number decides which Volume wins."""


@runtime_checkable
class SeriesSearch(Protocol):
    async def search(self, query: str) -> list[SeriesCandidate]: ...


@runtime_checkable
class SeriesLookup(Protocol):
    async def get_series(self, provider_id: str) -> SeriesCandidate: ...


@runtime_checkable
class SeriesCharacters(Protocol):
    async def get_character_names(self, provider_id: str) -> list[CharacterName]: ...


@runtime_checkable
class SeriesVolumes(Protocol):
    async def get_volume_chapters(self, provider_id: str) -> VolumeChapters: ...


@runtime_checkable
class SeriesLatestChapter(Protocol):
    async def get_latest_chapter(self, provider_id: str) -> Decimal | None: ...


@runtime_checkable
class SeriesVolumeMetadata(Protocol):
    async def get_volume_metadata(
        self, title: str, aliases: Sequence[str], thresholds: Thresholds
    ) -> list[VolumeMetadata]: ...
