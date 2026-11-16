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
    external_ids: dict[Provider, str]


@runtime_checkable
class SeriesSearch(Protocol):
    async def search(self, query: str) -> list[SeriesCandidate]: ...


@runtime_checkable
class SeriesLookup(Protocol):
    async def get_series(self, provider_id: str) -> SeriesCandidate: ...
