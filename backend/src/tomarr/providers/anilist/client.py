import httpx2

from tomarr.core.http import HttpClientFactory, HttpPolicy
from tomarr.providers.anilist.mapper import parse_character_names, parse_search, parse_series
from tomarr.providers.base import CharacterName, SeriesCandidate
from tomarr.providers.response import read_response, require_digits

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


class AniListClient:
    def __init__(self, factory: HttpClientFactory) -> None:
        self._factory = factory

    async def search(self, query: str, *, limit: int = 10) -> list[SeriesCandidate]:
        response = await self._post(_SEARCH, {"search": query, "perPage": limit})
        return read_response(PROVIDER_NAME, response, parse_search)

    async def get_series(self, provider_id: str) -> SeriesCandidate:
        response = await self._post(_SERIES, {"id": _media_id(provider_id)})
        return read_response(PROVIDER_NAME, response, parse_series)

    async def get_character_names(self, provider_id: str) -> list[CharacterName]:
        response = await self._post(_CHARACTERS, {"id": _media_id(provider_id)})
        return read_response(PROVIDER_NAME, response, parse_character_names)

    async def _post(self, query: str, variables: dict[str, str | int]) -> httpx2.Response:
        async with self._factory.client(POLICY, base_url=BASE_URL) as client:
            return await client.post("/", json={"query": query, "variables": variables})


def _media_id(provider_id: str) -> int:
    require_digits(PROVIDER_NAME, provider_id)
    return int(provider_id)
