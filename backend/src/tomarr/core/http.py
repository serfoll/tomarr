import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC
from email.utils import parsedate_to_datetime
from urllib.parse import unquote, urlsplit, urlunsplit

import httpx2
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tomarr.core.errors import RateLimited
from tomarr.core.rate_limit import RateLimiter
from tomarr.core.response_cache import CachedResponse, ResponseCache

logger = logging.getLogger(__name__)

# httpx2 logs every request URL at INFO, query string included, and some services put an API key
# there. httpcore2 logs the host and every response header, cookies included, at DEBUG. Calls are
# logged here by adapter name instead.
logging.getLogger("httpx2").setLevel(logging.WARNING)
logging.getLogger("httpcore2").setLevel(logging.WARNING)


@dataclass(frozen=True)
class HttpPolicy:
    """An adapter's limits. `name` is the service name a person sees ("Prowlarr"), and it also
    keys the shared rate limiter and the cache."""

    name: str
    requests: int
    interval: float
    cache_ttl: float = 0.0


def safe_url(url: str) -> str:
    return split_url_credentials(url)[0]


def split_url_credentials(url: str) -> tuple[str, str | None, str | None]:
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url, None, None
    host = parts.netloc.rpartition("@")[2]
    clean = urlunsplit(parts._replace(netloc=host))
    username = None if parts.username is None else unquote(parts.username)
    password = None if parts.password is None else unquote(parts.password)
    return clean, username, password


class HttpClientFactory:
    """Builds every outbound client. Each one goes through the adapter's rate limiter and the
    response cache, and clients of the same adapter name share one limiter."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        transport: httpx2.AsyncBaseTransport | None = None,
        clock: Callable[[], float],
        sleep: Callable[[float], Awaitable[None]],
        now: Callable[[], float],
    ) -> None:
        self._cache = ResponseCache(session_factory, now)
        self._transport = transport
        self._clock = clock
        self._sleep = sleep
        self._now = now
        self._limiters: dict[str, RateLimiter] = {}

    def client(
        self,
        policy: HttpPolicy,
        *,
        base_url: str = "",
        auth: httpx2.Auth | tuple[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx2.AsyncClient:
        if "@" in urlsplit(base_url).netloc:
            raise ValueError(
                f"The {policy.name} base URL carries credentials. Pass them with auth= or headers=."
            )
        limiter = self._limiters.get(policy.name)
        if limiter is None:
            limiter = RateLimiter(policy.requests, policy.interval, self._clock, self._sleep)
            self._limiters[policy.name] = limiter
        elif (limiter.requests, limiter.interval) != (policy.requests, policy.interval):
            raise ValueError(
                f"The {policy.name} policy has different limits from an earlier one with the "
                "same name."
            )
        inner = self._transport or httpx2.AsyncHTTPTransport()
        transport = _PolicyTransport(inner, policy, limiter, self._cache, self._now)
        return httpx2.AsyncClient(
            base_url=base_url, auth=auth, headers=headers, transport=transport
        )


class _PolicyTransport(httpx2.AsyncBaseTransport):
    def __init__(
        self,
        inner: httpx2.AsyncBaseTransport,
        policy: HttpPolicy,
        limiter: RateLimiter,
        cache: ResponseCache,
        now: Callable[[], float],
    ) -> None:
        self._inner = inner
        self._policy = policy
        self._limiter = limiter
        self._cache = cache
        self._now = now

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        name = self._policy.name
        if request.url.userinfo:
            raise ValueError(
                f"A {name} request URL carries credentials. Pass them with auth= or headers=."
            )
        url = str(request.url)
        cacheable = request.method == "GET" and self._policy.cache_ttl > 0
        if cacheable:
            cached = await self._cache.get(name, request.method, url)
            if cached is not None:
                return _replay(cached)
        await self._limiter.acquire()
        response = await self._inner.handle_async_request(request)
        if response.status_code == 429:
            await response.aclose()
            retry_after = _retry_after(response.headers.get("retry-after"), self._now())
            delay = "an unknown time" if retry_after is None else f"{retry_after:g} seconds"
            logger.warning("%s returned 429. Retry after %s.", name, delay)
            raise RateLimited(name, retry_after)
        if not cacheable or response.status_code != 200:
            return response
        # The stream is read directly, not through aread(), so the body is stored still
        # content-encoded and the client decodes it once, on the response returned here.
        assert isinstance(response.stream, httpx2.AsyncByteStream)
        try:
            body = b"".join([chunk async for chunk in response.stream])
        finally:
            await response.aclose()
        # Header bytes are stored as latin-1 text, which maps every byte to one character, so a
        # replay sends back exactly the bytes the service sent, non-ASCII ones included.
        headers = [
            (key.decode("latin-1"), value.decode("latin-1")) for key, value in response.headers.raw
        ]
        stored = CachedResponse(response.status_code, headers, body)
        await self._cache.put(name, request.method, url, stored, self._policy.cache_ttl)
        return _replay(stored)

    async def aclose(self) -> None:
        await self._inner.aclose()


def _replay(stored: CachedResponse) -> httpx2.Response:
    headers = [(key.encode("latin-1"), value.encode("latin-1")) for key, value in stored.headers]
    return httpx2.Response(
        stored.status_code, headers=headers, stream=httpx2.ByteStream(stored.body)
    )


def _retry_after(value: str | None, now: float) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(int(value))
    except OverflowError:
        return None
    except ValueError:
        try:
            moment = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        seconds = moment.timestamp() - now
    return max(seconds, 0.0)
