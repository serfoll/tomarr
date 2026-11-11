import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tomarr.domain.http_cache import HttpCacheEntry


@dataclass(frozen=True)
class CachedResponse:
    status_code: int
    headers: list[tuple[str, str]]
    # Raw bytes as received, still content-encoded, so a replay decodes like a live response.
    body: bytes


class ResponseCache:
    """Stores responses keyed by a hash of adapter, method and URL. The URL is never stored,
    because some Providers put an API key in the query string."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], now: Callable[[], float]
    ) -> None:
        self._session_factory = session_factory
        self._now = now

    async def get(self, adapter: str, method: str, url: str) -> CachedResponse | None:
        async with self._session_factory() as session:
            row = await session.get(HttpCacheEntry, _key(adapter, method, url))
        if row is None or row.expires_at <= self._now():
            return None
        return CachedResponse(
            status_code=row.status_code,
            headers=[(name, value) for name, value in row.headers],
            body=row.body,
        )

    async def put(
        self, adapter: str, method: str, url: str, response: CachedResponse, ttl: float
    ) -> None:
        values = {
            "adapter": adapter,
            "status_code": response.status_code,
            "headers": [[name, value] for name, value in response.headers],
            "body": response.body,
            "expires_at": self._now() + ttl,
        }
        statement = insert(HttpCacheEntry).values(key=_key(adapter, method, url), **values)
        statement = statement.on_conflict_do_update(
            index_elements=[HttpCacheEntry.key], set_=values
        )
        async with self._session_factory.begin() as session:
            await session.execute(statement)


def _key(adapter: str, method: str, url: str) -> str:
    # httpx2 rejects a NUL anywhere in a URL and the transport caches only GET, so neither of
    # those parts can hold the separator. Nothing checks the adapter name: one with a NUL in it
    # could share a key with another adapter.
    return hashlib.sha256(f"{adapter}\0{method}\0{url}".encode()).hexdigest()
