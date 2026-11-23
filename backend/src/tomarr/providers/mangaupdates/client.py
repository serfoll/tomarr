from decimal import Decimal

import httpx2

from tomarr.core.http import HttpClientFactory, HttpPolicy
from tomarr.core.version import USER_AGENT
from tomarr.providers.mangaupdates.mapper import parse_series
from tomarr.providers.response import UNREADABLE, read_response, require_base36

PROVIDER_NAME = "MangaUpdates"
BASE_URL = "https://api.mangaupdates.com/v1"

# MangaUpdates states no limit. It asks for reasonable spacing between requests and for responses
# to be cached, so 1 request per second is a guess, and so is the one hour cache.
POLICY = HttpPolicy(PROVIDER_NAME, requests=1, interval=1, cache_ttl=3600)


class MangaUpdatesClient:
    def __init__(self, factory: HttpClientFactory) -> None:
        self._factory = factory

    async def get_latest_chapter(self, provider_id: str) -> Decimal | None:
        # The ID goes into the path, so anything but base 36 could reach another endpoint.
        require_base36(PROVIDER_NAME, provider_id)
        response = await self._get(f"/series/{int(provider_id, 36)}")
        return read_response(PROVIDER_NAME, response, parse_series)

    async def _get(self, path: str) -> httpx2.Response:
        # A 200 the parser cannot read is not cached. It still reaches read_response, which raises.
        def accept(response: httpx2.Response) -> bool:
            try:
                parse_series(response.json())
            except UNREADABLE:
                return False
            return True

        async with self._factory.client(
            POLICY, base_url=BASE_URL, headers={"User-Agent": USER_AGENT}, accept=accept
        ) as client:
            return await client.get(path)
