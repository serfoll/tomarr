from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from tomarr.domain.external_id import Provider
from tomarr.domain.series import Format


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
