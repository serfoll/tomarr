from decimal import Decimal

from pydantic import BaseModel

from tomarr.domain.external_id import Provider
from tomarr.domain.series import Format
from tomarr.providers.base import CharacterName, SeriesCandidate

_LONG_STRIP = "Long Strip"
_PRINT_FORMATS = {"MANGA", "ONE_SHOT"}
_COUNTRY_FORMATS = {
    "JP": Format.MANGA,
    "KR": Format.MANHWA,
    "CN": Format.MANHUA,
    "TW": Format.MANHUA,
    "HK": Format.MANHUA,
}


# GraphQL reports a failure in `errors`, even on a 200. Typing it as None makes any entry a
# validation error, so a partial answer is refused like any other unreadable body.
class _Response(BaseModel):
    errors: None = None


class _Title(BaseModel):
    romaji: str
    english: str | None
    native: str | None


class _CoverImage(BaseModel):
    extraLarge: str | None
    large: str | None


class _Tag(BaseModel):
    name: str
    isMediaSpoiler: bool | None


class _Media(BaseModel):
    id: int
    title: _Title
    format: str | None
    status: str | None
    chapters: int | None
    volumes: int | None
    countryOfOrigin: str | None
    coverImage: _CoverImage | None
    synonyms: list[str | None] | None
    tags: list[_Tag] | None


class _Page(BaseModel):
    media: list[_Media]


class _SearchData(BaseModel):
    Page: _Page


class _SearchResponse(_Response):
    data: _SearchData


class _MediaData(BaseModel):
    Media: _Media


class _SeriesResponse(_Response):
    data: _MediaData


class _CharacterName(BaseModel):
    full: str | None
    native: str | None
    alternative: list[str | None] | None


class _CharacterNode(BaseModel):
    name: _CharacterName


class _CharacterEdge(BaseModel):
    node: _CharacterNode


class _Characters(BaseModel):
    edges: list[_CharacterEdge]


class _CharactersMedia(BaseModel):
    characters: _Characters


class _CharactersData(BaseModel):
    Media: _CharactersMedia


class _CharactersResponse(_Response):
    data: _CharactersData


def parse_search(payload: object) -> list[SeriesCandidate]:
    return [
        _to_candidate(media) for media in _SearchResponse.model_validate(payload).data.Page.media
    ]


def parse_series(payload: object) -> SeriesCandidate:
    return _to_candidate(_SeriesResponse.model_validate(payload).data.Media)


def parse_character_names(payload: object) -> list[CharacterName]:
    edges = _CharactersResponse.model_validate(payload).data.Media.characters.edges
    return [
        CharacterName(
            full=name.full,
            native=name.native or None,
            alternatives=tuple(_present(name.alternative or ())),
        )
        for name in (edge.node.name for edge in edges)
        if name.full
    ]


def _to_candidate(media: _Media) -> SeriesCandidate:
    title = media.title.english or media.title.romaji
    others = (media.title.english, media.title.romaji, media.title.native, *(media.synonyms or ()))
    return SeriesCandidate(
        provider=Provider.ANILIST,
        provider_id=str(media.id),
        title=title,
        aliases=tuple(alias for alias in _present(others) if alias != title),
        format=_format(media),
        status=media.status,
        total_volumes=None if media.volumes is None else Decimal(media.volumes),
        total_chapters=None if media.chapters is None else Decimal(media.chapters),
        external_ids={},
        cover_url=_cover(media.coverImage),
    )


def _present(names: tuple[str | None, ...] | list[str | None]) -> list[str]:
    return list(dict.fromkeys(name for name in names if name))


def _cover(cover: _CoverImage | None) -> str | None:
    if cover is None:
        return None
    return cover.extraLarge or cover.large or None


# AniList has no webtoon or manhua format, so both come from the Long Strip tag and the country.
def _format(media: _Media) -> Format | None:
    if media.format not in _PRINT_FORMATS:
        return None
    if any(tag.name == _LONG_STRIP and not tag.isMediaSpoiler for tag in media.tags or ()):
        return Format.WEBTOON
    return _COUNTRY_FORMATS.get(media.countryOfOrigin or "")
