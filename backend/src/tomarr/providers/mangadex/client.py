import httpx2

from tomarr.core.http import HttpClientFactory, HttpPolicy
from tomarr.core.version import USER_AGENT
from tomarr.providers.base import VolumeChapters
from tomarr.providers.mangadex.mapper import parse_aggregate
from tomarr.providers.response import UNREADABLE, read_response, require_uuid

PROVIDER_NAME = "MangaDex"
BASE_URL = "https://api.mangadex.org"

# MangaDex allows about 5 requests per second per IP, answers 429 above that and blocks the IP
# with 403 if requests keep coming. The one hour cache is a judgment, since MangaDex's docs give
# no client advice on caching.
POLICY = HttpPolicy(PROVIDER_NAME, requests=5, interval=1, cache_ttl=3600)


class MangaDexClient:
    def __init__(self, factory: HttpClientFactory) -> None:
        self._factory = factory

    async def get_volume_chapters(self, provider_id: str) -> VolumeChapters:
        # The ID goes into the path, so anything but a UUID could reach another endpoint.
        require_uuid(PROVIDER_NAME, provider_id)
        response = await self._get(f"/manga/{provider_id}/aggregate", {"includeUnavailable": 1})
        return read_response(PROVIDER_NAME, response, parse_aggregate)

    async def _get(self, path: str, params: dict[str, str | int]) -> httpx2.Response:
        # A 200 the parser cannot read is not cached. It still reaches read_response, which raises.
        def accept(response: httpx2.Response) -> bool:
            try:
                parse_aggregate(response.json())
            except UNREADABLE:
                return False
            return True

        async with self._factory.client(
            POLICY, base_url=BASE_URL, headers={"User-Agent": USER_AGENT}, accept=accept
        ) as client:
            return await client.get(path, params=params)
