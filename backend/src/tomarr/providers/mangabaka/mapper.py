from decimal import Decimal

from pydantic import BaseModel

from tomarr.domain.external_id import Provider
from tomarr.domain.series import Format
from tomarr.providers.base import SeriesCandidate

_FORMATS = {"manga": Format.MANGA, "manhwa": Format.MANHWA, "manhua": Format.MANHUA}


class _SourceEntry(BaseModel):
    id: int | str | None


class _Source(BaseModel):
    anilist: _SourceEntry
    manga_updates: _SourceEntry


class _AltTitle(BaseModel):
    title: str


class _Series(BaseModel):
    id: int
    title: str
    titles: list[_AltTitle] | None = None
    type: str
    status: str
    final_volume: Decimal | None
    total_chapters: Decimal | None
    source: _Source


class _SearchResponse(BaseModel):
    data: list[_Series]


class _SeriesResponse(BaseModel):
    data: _Series


def parse_search(payload: object) -> list[SeriesCandidate]:
    return [_to_candidate(series) for series in _SearchResponse.model_validate(payload).data]


def parse_series(payload: object) -> SeriesCandidate:
    return _to_candidate(_SeriesResponse.model_validate(payload).data)


def _to_candidate(series: _Series) -> SeriesCandidate:
    aliases = dict.fromkeys(alt.title for alt in series.titles or () if alt.title != series.title)
    external_ids = {
        provider: str(entry.id)
        for provider, entry in (
            (Provider.ANILIST, series.source.anilist),
            (Provider.MANGAUPDATES, series.source.manga_updates),
        )
        if entry.id is not None and str(entry.id).strip()
    }
    return SeriesCandidate(
        provider=Provider.MANGABAKA,
        provider_id=str(series.id),
        title=series.title,
        aliases=tuple(aliases),
        format=_FORMATS.get(series.type),
        status=series.status,
        total_volumes=series.final_volume,
        total_chapters=series.total_chapters,
        external_ids=external_ids,
    )
