from collections.abc import Callable

import httpx2

from tomarr.core.http import HttpClientFactory, HttpPolicy
from tomarr.providers.base import SeriesCandidate
from tomarr.providers.mangabaka.mapper import parse_search, parse_series
from tomarr.providers.response import UNREADABLE, read_response, require_digits

PROVIDER_NAME = "MangaBaka"
BASE_URL = "https://api.mangabaka.org"

# MangaBaka allows search 30 times a minute with a burst of 5, and everything else more. One
# policy covers both, so it takes the stricter search limit as 5 requests per 10 seconds. The one
# hour cache is a judgment, since MangaBaka's docs give a CDN TTL and no client advice.
POLICY = HttpPolicy(PROVIDER_NAME, requests=5, interval=10, cache_ttl=3600)


class MangaBakaClient:
    def __init__(self, factory: HttpClientFactory) -> None:
        self._factory = factory

    async def search(self, query: str, *, limit: int = 10) -> list[SeriesCandidate]:
        response = await self._get("/v1/series/search", parse_search, {"q": query, "limit": limit})
        return read_response(PROVIDER_NAME, response, parse_search)

    async def get_series(self, provider_id: str) -> SeriesCandidate:
        # The ID goes into the path, so anything but digits could reach another endpoint.
        require_digits(PROVIDER_NAME, provider_id)
        response = await self._get(f"/v1/series/{provider_id}", parse_series)
        return read_response(PROVIDER_NAME, response, parse_series)

    async def _get(
        self,
        path: str,
        parse: Callable[[object], object],
        params: dict[str, str | int] | None = None,
    ) -> httpx2.Response:
        # A 200 the parser cannot read is not cached. It still reaches read_response, which raises.
        def accept(response: httpx2.Response) -> bool:
            try:
                parse(response.json())
            except UNREADABLE:
                return False
            return True

        async with self._factory.client(POLICY, base_url=BASE_URL, accept=accept) as client:
            return await client.get(path, params=params)
