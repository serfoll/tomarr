import logging
from collections.abc import Callable

import httpx2
from pydantic import ValidationError

from tomarr.core.errors import ProviderError
from tomarr.core.http import HttpClientFactory, HttpPolicy
from tomarr.providers.anilist.mapper import parse_character_names, parse_search, parse_series
from tomarr.providers.base import CharacterName, SeriesCandidate

logger = logging.getLogger(__name__)

PROVIDER_NAME = "AniList"
BASE_URL = "https://graphql.anilist.co"

# AniList documents 90 requests a minute, lowered to 30 for now, plus a burst limiter whose size it
# does not say. A POST is never cached, so every call uses a slot.
POLICY = HttpPolicy(PROVIDER_NAME, requests=30, interval=60)

_MEDIA_FIELDS = """
fragment MediaFields on Media {
  id
  title { romaji english native }
  format
  status
  chapters
  volumes
  countryOfOrigin
  isAdult
  coverImage { extraLarge large }
  synonyms
  tags { name rank isMediaSpoiler }
}
"""

_SEARCH = (
    """
query ($search: String!, $perPage: Int!) {
  Page(perPage: $perPage) {
    media(search: $search, type: MANGA) { ...MediaFields }
  }
}
"""
    + _MEDIA_FIELDS
)

_SERIES = (
    """
query ($id: Int!) {
  Media(id: $id, type: MANGA) { ...MediaFields }
}
"""
    + _MEDIA_FIELDS
)

# Ordered by role, so the main characters come first.
_CHARACTERS = """
query ($id: Int!) {
  Media(id: $id, type: MANGA) {
    characters(sort: ROLE, perPage: 25) {
      edges { role node { name { full native alternative } } }
    }
  }
}
"""

# What a body can raise when it is not JSON, not UTF-8, not the shape the parser reads
# (ValidationError is a ValueError), or nested too deep.
_UNREADABLE = (ValueError, RecursionError)


class AniListClient:
    def __init__(self, factory: HttpClientFactory) -> None:
        self._factory = factory

    async def search(self, query: str, *, limit: int = 10) -> list[SeriesCandidate]:
        response = await self._post(_SEARCH, {"search": query, "perPage": limit})
        return _read(response, parse_search)

    async def get_series(self, provider_id: str) -> SeriesCandidate:
        response = await self._post(_SERIES, {"id": _media_id(provider_id)})
        return _read(response, parse_series)

    async def get_character_names(self, provider_id: str) -> list[CharacterName]:
        response = await self._post(_CHARACTERS, {"id": _media_id(provider_id)})
        return _read(response, parse_character_names)

    async def _post(self, query: str, variables: dict[str, str | int]) -> httpx2.Response:
        async with self._factory.client(POLICY, base_url=BASE_URL) as client:
            return await client.post("/", json={"query": query, "variables": variables})


def _media_id(provider_id: str) -> int:
    if not (provider_id.isascii() and provider_id.isdigit()):
        raise ValueError("An AniList series ID is made of digits only.")
    return int(provider_id)


def _read[T](response: httpx2.Response, parse: Callable[[object], T]) -> T:
    if response.status_code != 200:
        raise ProviderError(PROVIDER_NAME, response.status_code)
    try:
        return parse(response.json())
    except ValidationError as error:
        # Only where and what kind: the input values are the provider's body.
        problems = ", ".join(
            f"{'.'.join(str(part) for part in detail['loc'])} ({detail['type']})"
            for detail in error.errors()
        )
        logger.warning("%s sent a body Tomarr does not recognize: %s.", PROVIDER_NAME, problems)
        raise ProviderError(PROVIDER_NAME, response.status_code) from None
    except _UNREADABLE as error:
        logger.warning("%s sent a body that is not JSON (%s).", PROVIDER_NAME, type(error).__name__)
        raise ProviderError(PROVIDER_NAME, response.status_code) from None
