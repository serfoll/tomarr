from collections.abc import Sequence

import httpx2

from tomarr.core.http import HttpClientFactory, HttpPolicy
from tomarr.core.version import USER_AGENT
from tomarr.providers.base import VolumeDetails
from tomarr.providers.googlebooks.mapper import parse_volume_details
from tomarr.providers.response import UNREADABLE, read_response

PROVIDER_NAME = "Google Books"
BASE_URL = "https://www.googleapis.com/books/v1"

# Google states no per-second limit a user can rely on, and the daily quota is per key and not
# published here. One request a second and a one day cache are judgments. The limiter spaces
# request starts and does not hold a request open.
POLICY = HttpPolicy(PROVIDER_NAME, requests=1, interval=1, cache_ttl=86400)

_FIELDS = "items(volumeInfo(description,publishedDate,imageLinks,industryIdentifiers))"


class GoogleBooksClient:
    def __init__(self, factory: HttpClientFactory, api_key: str) -> None:
        self._factory = factory
        self._api_key = api_key.strip()
        if any(c.isspace() or not c.isprintable() for c in self._api_key):
            raise ValueError(f"{PROVIDER_NAME} API key has whitespace or control characters in it.")

    async def get_volume_details(self, isbns: Sequence[str]) -> dict[str, VolumeDetails]:
        if not self._api_key:
            raise ValueError(f"{PROVIDER_NAME} needs an API key.")
        for isbn in isbns:
            _require_isbn(isbn)
        details: dict[str, VolumeDetails] = {}
        # One after another, so the limiter spaces them and one failure stops the call.
        for isbn in isbns:
            response = await self._get(isbn)
            found = read_response(
                PROVIDER_NAME, response, lambda body, isbn=isbn: parse_volume_details(body, isbn)
            )
            if found is not None:
                details[isbn] = found
        return details

    async def _get(self, isbn: str) -> httpx2.Response:
        # A 200 the parser cannot read is not cached. It still reaches read_response, which raises.
        def accept(response: httpx2.Response) -> bool:
            try:
                parse_volume_details(response.json(), isbn)
            except UNREADABLE:
                return False
            return True

        params = {"q": f"isbn:{isbn}", "fields": _FIELDS}
        headers = {"User-Agent": USER_AGENT, "x-goog-api-key": self._api_key}
        async with self._factory.client(
            POLICY, base_url=BASE_URL, headers=headers, accept=accept
        ) as client:
            return await client.get("/volumes", params=params)


def _require_isbn(isbn: str) -> None:
    # The ISBN goes into the q parameter, where anything but digits could add a search term.
    if not (isbn.isascii() and isbn.isdigit() and len(isbn) == 13):
        raise ValueError(f"{PROVIDER_NAME} ISBNs are 13 digits.")
