from decimal import Decimal
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, model_validator

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


def _usable(name: str | None) -> str | None:
    if name is None:
        return None
    return name.strip() or None


# A name that is blank once stripped is absent, wherever AniList sends one.
type _Name = Annotated[str | None, AfterValidator(_usable)]


# GraphQL reports a failure in `errors`, even on a 200. Typing it as None makes any entry a
# validation error, so a partial answer is refused like any other unreadable body.
class _Response(BaseModel):
    errors: None = None


class _Title(BaseModel):
    romaji: _Name
    english: _Name
    native: _Name

    # Any one of the three can be null, but a series with none of them cannot be shown.
    @model_validator(mode="after")
    def _has_a_title(self) -> Self:
        if self.english is None and self.romaji is None and self.native is None:
            raise ValueError("The series has no title.")
        return self


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
    synonyms: list[_Name] | None
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
    full: _Name
    native: _Name
    alternative: list[_Name] | None


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
    # The glossary holds names in every script, so a character known only by its native name stays.
    return [
        CharacterName(
            full=full,
            native=name.native,
            alternatives=tuple(_present(name.alternative or ())),
        )
        for name in (edge.node.name for edge in edges)
        if (full := name.full or name.native)
    ]


def _to_candidate(media: _Media) -> SeriesCandidate:
    # The first name is the title: English, else romaji, else native. _Title makes sure one exists.
    title, *aliases = _present(
        (media.title.english, media.title.romaji, media.title.native, *(media.synonyms or ()))
    )
    return SeriesCandidate(
        provider=Provider.ANILIST,
        provider_id=str(media.id),
        title=title,
        aliases=tuple(aliases),
        format=_format(media),
        status=media.status,
        total_volumes=None if media.volumes is None else Decimal(media.volumes),
        total_chapters=None if media.chapters is None else Decimal(media.chapters),
        external_ids={},
        cover_url=_cover(media.coverImage),
    )


def _present(names: tuple[str | None, ...] | list[str | None]) -> list[str]:
    return list(dict.fromkeys(name for name in names if name is not None))


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
