import logging
from collections.abc import Callable

import httpx2
from pydantic import ValidationError

from tomarr.core.errors import ProviderError
from tomarr.core.http import HttpClientFactory, HttpPolicy
from tomarr.providers.base import SeriesCandidate
from tomarr.providers.mangabaka.mapper import parse_search, parse_series

logger = logging.getLogger(__name__)

PROVIDER_NAME = "MangaBaka"
BASE_URL = "https://api.mangabaka.org"

# MangaBaka allows search 30 times a minute with a burst of 5, and everything else more. One
# policy covers both, so it takes the stricter search limit as 5 requests per 10 seconds. The one
# hour cache is a judgment, since MangaBaka's docs give a CDN TTL and no client advice.
POLICY = HttpPolicy(PROVIDER_NAME, requests=5, interval=10, cache_ttl=3600)

# What a body can raise when it is not JSON, not UTF-8, not the shape the parser reads
# (ValidationError is a ValueError), or nested too deep. _read and the cache's accept check
# share this, so they cannot disagree about what is usable.
_UNREADABLE = (ValueError, RecursionError)


class MangaBakaClient:
    def __init__(self, factory: HttpClientFactory) -> None:
        self._factory = factory

    async def search(self, query: str, *, limit: int = 10) -> list[SeriesCandidate]:
        response = await self._get("/v1/series/search", parse_search, {"q": query, "limit": limit})
        return _read(response, parse_search)

    async def get_series(self, provider_id: str) -> SeriesCandidate:
        # The ID goes into the path, so anything but digits could reach another endpoint.
        if not (provider_id.isascii() and provider_id.isdigit()):
            raise ValueError("A MangaBaka series ID is made of digits only.")
        response = await self._get(f"/v1/series/{provider_id}", parse_series)
        return _read(response, parse_series)

    async def _get(
        self,
        path: str,
        parse: Callable[[object], object],
        params: dict[str, str | int] | None = None,
    ) -> httpx2.Response:
        # A 200 the parser cannot read is returned to _read, which raises, but it is not cached.
        def accept(response: httpx2.Response) -> bool:
            try:
                parse(response.json())
            except _UNREADABLE:
                return False
            return True

        async with self._factory.client(POLICY, base_url=BASE_URL, accept=accept) as client:
            return await client.get(path, params=params)


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
