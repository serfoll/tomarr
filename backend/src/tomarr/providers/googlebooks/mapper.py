import re
from datetime import date

from pydantic import BaseModel, Field

from tomarr.providers.base import DatePrecision, VolumeDetails

_PUBLISHED = re.compile(r"([0-9]{4})-([0-9]{2})(?:-([0-9]{2}))?")


class _ImageLinks(BaseModel):
    smallThumbnail: str | None = None
    thumbnail: str | None = None


class _Identifier(BaseModel):
    type: str
    identifier: str


class _VolumeInfo(BaseModel):
    description: str | None = None
    publishedDate: str | None = None
    imageLinks: _ImageLinks | None = None
    industryIdentifiers: list[_Identifier] = Field(default_factory=list[_Identifier])


class _Item(BaseModel):
    volumeInfo: _VolumeInfo = Field(default_factory=_VolumeInfo)


class _Response(BaseModel):
    items: list[_Item] = Field(default_factory=list[_Item])


def parse_volume_details(body: object, isbn: str) -> VolumeDetails | None:
    """Read what Google Books says about the Volume with this ISBN-13, or None when no item has it.

    Raises ValueError when the body is not the shape the search returns.
    """
    for item in _Response.model_validate(body).items:
        info = item.volumeInfo
        if any(i.type == "ISBN_13" and i.identifier == isbn for i in info.industryIdentifiers):
            release_date, precision = _read_published(info.publishedDate)
            return VolumeDetails(
                synopsis=(info.description or "").strip() or None,
                cover_url=_read_cover(info.imageLinks),
                release_date=release_date,
                release_precision=precision,
            )
    return None


def _read_cover(links: _ImageLinks | None) -> str | None:
    if links is None:
        return None
    url = links.thumbnail or links.smallThumbnail
    if not url:
        return None
    # Google serves the same image over https, and the links come back as http.
    if url.startswith("http://"):
        return "https://" + url.removeprefix("http://")
    return url


def _read_published(text: str | None) -> tuple[date | None, DatePrecision | None]:
    match = _PUBLISHED.fullmatch(text) if text else None
    if match is None:
        return None, None
    year, month, day = int(match[1]), int(match[2]), match[3]
    try:
        published = date(year, month, int(day) if day else 1)
    except ValueError:
        return None, None
    return published, DatePrecision.DAY if day else DatePrecision.MONTH
