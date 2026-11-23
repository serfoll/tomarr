from decimal import Decimal

from tomarr.core.http import HttpClientFactory


class MangaUpdatesClient:
    def __init__(self, factory: HttpClientFactory) -> None:
        self._factory = factory

    async def get_latest_chapter(self, provider_id: str) -> Decimal | None:
        raise NotImplementedError
