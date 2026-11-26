import logging
from collections.abc import Sequence

import httpx2

from tomarr.core.errors import ProviderError
from tomarr.core.http import HttpClientFactory, HttpPolicy
from tomarr.core.version import USER_AGENT
from tomarr.matching.thresholds import Thresholds
from tomarr.providers.base import VolumeMetadata
from tomarr.providers.ndl.mapper import parse_volumes
from tomarr.providers.response import UNREADABLE

logger = logging.getLogger(__name__)

PROVIDER_NAME = "NDL"
BASE_URL = "https://ndlsearch.ndl.go.jp"

# NDL limits concurrent requests, may block a server that sends many, and states no number.
# One request every two seconds and a one hour cache are guesses. The limiter spaces request
# starts and does not hold a request open, so two calls can still overlap when NDL answers slowly.
POLICY = HttpPolicy(PROVIDER_NAME, requests=1, interval=2, cache_ttl=3600)

# 726 is NDL's classification for manga, matched as a prefix. 500 is the most a query returns.
_NDC_MANGA = "726"
_MAX_RESULTS = "500"


class NdlClient:
    def __init__(self, factory: HttpClientFactory) -> None:
        self._factory = factory

    async def get_volume_metadata(
        self, title: str, aliases: Sequence[str], thresholds: Thresholds
    ) -> list[VolumeMetadata]:
        response = await self._get(title, aliases, thresholds)
        if response.status_code != 200:
            raise ProviderError(PROVIDER_NAME, response.status_code)
        try:
            return parse_volumes(response.content, title, aliases, thresholds)
        except UNREADABLE as error:
            logger.warning("%s sent a body that is not an RSS feed (%s).", PROVIDER_NAME, error)
            raise ProviderError(PROVIDER_NAME, response.status_code) from None

    async def _get(
        self, title: str, aliases: Sequence[str], thresholds: Thresholds
    ) -> httpx2.Response:
        # A 200 the mapper cannot read is not cached. It still reaches get_volume_metadata, which
        # raises.
        def accept(response: httpx2.Response) -> bool:
            try:
                parse_volumes(response.content, title, aliases, thresholds)
            except UNREADABLE:
                return False
            return True

        params = {"title": title, "ndc": _NDC_MANGA, "cnt": _MAX_RESULTS}
        async with self._factory.client(
            POLICY, base_url=BASE_URL, headers={"User-Agent": USER_AGENT}, accept=accept
        ) as client:
            return await client.get("/api/opensearch", params=params)
